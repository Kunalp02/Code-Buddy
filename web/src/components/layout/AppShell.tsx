import { Link } from "react-router-dom";

interface Props {
  children: React.ReactNode;
}

export default function AppShell({ children }: Props) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden>AF</span>
          <span className="brand-text">
            <strong>Arcfold</strong>
            <small>Codebase intelligence</small>
          </span>
        </Link>
        <nav className="app-header-nav">
          <a href="https://github.com/Kunalp02/Code-Buddy" target="_blank" rel="noreferrer" className="header-link">
            GitHub
          </a>
        </nav>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <span>Arcfold — map, document, and navigate your repositories</span>
      </footer>
    </div>
  );
}
