using System.Text.Json;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.FindSymbols;
using Microsoft.CodeAnalysis.MSBuild;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: Arcfold.Roslyn <project-root> <output.json>");
    return 1;
}

var root = Path.GetFullPath(args[0]);
var outputPath = Path.GetFullPath(args[1]);

MSBuildLocator.RegisterDefaults();

var result = new AnalysisResult();
var projectFiles = Directory.EnumerateFiles(root, "*.csproj", SearchOption.AllDirectories).Take(16).ToList();
var solutionPath = Directory.EnumerateFiles(root, "*.sln", SearchOption.AllDirectories).FirstOrDefault();

try
{
    using var workspace = MSBuildWorkspace.Create();
    var projects = new List<Project>();

    if (solutionPath is not null)
    {
        var solution = await workspace.OpenSolutionAsync(solutionPath);
        projects.AddRange(solution.Projects);
    }
    else
    {
        foreach (var csproj in projectFiles)
        {
            try
            {
                projects.Add(await workspace.OpenProjectAsync(csproj));
            }
            catch
            {
                // skip unloadable projects
            }
        }
    }

    if (projects.Count == 0)
    {
        result.Skipped = true;
        result.Reason = "No loadable .NET projects";
        await WriteOutput(outputPath, result);
        return 0;
    }

    var projectFileSet = new HashSet<string>(
        projects.SelectMany(p => p.Documents.Select(d => Rel(root, d.FilePath))),
        StringComparer.OrdinalIgnoreCase);

    foreach (var project in projects)
    {
        var relProject = Rel(root, project.FilePath ?? project.Name);
        result.Projects.Add(new ProjectInfoDto { Name = project.Name, Path = relProject });

        var compilation = await project.GetCompilationAsync();
        if (compilation is null) continue;

        foreach (var tree in compilation.SyntaxTrees)
        {
            if (tree.FilePath is null) continue;
            var relFile = Rel(root, tree.FilePath);
            var model = compilation.GetSemanticModel(tree);
            var rootNode = await tree.GetRootAsync();

            foreach (var node in rootNode.DescendantNodes())
            {
                var symbol = model.GetDeclaredSymbol(node);
                if (symbol is null || symbol.IsImplicitlyDeclared) continue;

                var line = tree.GetLineSpan(node.Span).StartLinePosition.Line + 1;
                var dto = new SymbolDto
                {
                    QualifiedName = symbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
                    Name = symbol.Name,
                    Kind = symbol.Kind.ToString().ToLowerInvariant(),
                    File = relFile,
                    Line = line,
                    EndLine = tree.GetLineSpan(node.Span).EndLinePosition.Line + 1,
                    Container = symbol.ContainingType?.ToDisplayString() ?? symbol.ContainingNamespace?.ToDisplayString(),
                };

                if (symbol is IMethodSymbol method)
                {
                    dto.Signature = method.ToDisplayString(SymbolDisplayFormat.MinimallyQualifiedFormat);
                    foreach (var attr in method.GetAttributes())
                    {
                        var attrName = attr.AttributeClass?.Name ?? "";
                        if (attrName.Contains("Http", StringComparison.OrdinalIgnoreCase) ||
                            attrName.Contains("Route", StringComparison.OrdinalIgnoreCase))
                        {
                            var route = ExtractRoute(attr);
                            if (route is not null)
                            {
                                result.Routes.Add(new RouteDto
                                {
                                    Method = HttpMethodFromAttribute(attrName),
                                    Path = route,
                                    Handler = method.Name,
                                    File = relFile,
                                    Line = line,
                                });
                            }
                        }
                    }
                }

                result.Symbols.Add(dto);
            }
        }
    }

    foreach (var project in projects)
    {
        var compilation = await project.GetCompilationAsync();
        if (compilation is null) continue;

        var symbols = result.Symbols
            .Where(s => projectFileSet.Contains(s.File))
            .Where(s => s.Kind is "method" or "class" or "interface" or "property")
            .Take(200);

        foreach (var symDto in symbols)
        {
            var symbol = compilation.GetSymbolsWithName(symDto.Name, SymbolFilter.All)
                .FirstOrDefault(s =>
                    s.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat) == symDto.QualifiedName);
            if (symbol is null) continue;

            try
            {
                var refs = await SymbolFinder.FindReferencesAsync(symbol, project.Solution);
                foreach (var refSym in refs)
                {
                    foreach (var loc in refSym.Locations.Take(15))
                    {
                        if (loc.Location.SourceTree?.FilePath is null) continue;
                        result.References.Add(new ReferenceDto
                        {
                            FromFile = Rel(root, loc.Location.SourceTree.FilePath),
                            FromLine = loc.Location.GetLineSpan().StartLinePosition.Line + 1,
                            ToQualifiedName = symDto.QualifiedName,
                            ToName = symDto.Name,
                            Kind = "roslyn",
                        });
                    }
                }
            }
            catch
            {
                // skip symbols that fail reference search
            }
        }
    }

    result.Success = true;
}
catch (Exception ex)
{
    result.Success = false;
    result.Reason = ex.Message;
}

await WriteOutput(outputPath, result);
return result.Success ? 0 : 2;

static string Rel(string root, string? path) =>
    path is null ? "" : Path.GetRelativePath(root, path).Replace('\\', '/');

static async Task WriteOutput(string path, AnalysisResult result)
{
    var json = JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true });
    await File.WriteAllTextAsync(path, json);
}

static string? ExtractRoute(AttributeData attr)
{
    if (attr.ConstructorArguments.Length > 0 && attr.ConstructorArguments[0].Value is string s)
        return s;
    foreach (var named in attr.NamedArguments)
    {
        if (named.Key is "Template" or "template" && named.Value.Value is string t)
            return t;
    }
    return null;
}

static string HttpMethodFromAttribute(string attrName)
{
    if (attrName.Contains("Post", StringComparison.OrdinalIgnoreCase)) return "POST";
    if (attrName.Contains("Put", StringComparison.OrdinalIgnoreCase)) return "PUT";
    if (attrName.Contains("Delete", StringComparison.OrdinalIgnoreCase)) return "DELETE";
    if (attrName.Contains("Patch", StringComparison.OrdinalIgnoreCase)) return "PATCH";
    return "GET";
}

sealed class AnalysisResult
{
    public bool Success { get; set; }
    public bool Skipped { get; set; }
    public string? Reason { get; set; }
    public List<ProjectInfoDto> Projects { get; set; } = [];
    public List<SymbolDto> Symbols { get; set; } = [];
    public List<ReferenceDto> References { get; set; } = [];
    public List<RouteDto> Routes { get; set; } = [];
}

sealed class ProjectInfoDto
{
    public string Name { get; set; } = "";
    public string Path { get; set; } = "";
}

sealed class SymbolDto
{
    public string QualifiedName { get; set; } = "";
    public string Name { get; set; } = "";
    public string Kind { get; set; } = "";
    public string File { get; set; } = "";
    public int Line { get; set; }
    public int EndLine { get; set; }
    public string? Container { get; set; }
    public string? Signature { get; set; }
}

sealed class ReferenceDto
{
    public string FromFile { get; set; } = "";
    public int FromLine { get; set; }
    public string ToQualifiedName { get; set; } = "";
    public string ToName { get; set; } = "";
    public string Kind { get; set; } = "reference";
}

sealed class RouteDto
{
    public string Method { get; set; } = "GET";
    public string Path { get; set; } = "";
    public string? Handler { get; set; }
    public string File { get; set; } = "";
    public int Line { get; set; }
}
