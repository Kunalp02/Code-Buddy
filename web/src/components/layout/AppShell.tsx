import { Link } from "react-router-dom";

interface Props {
  children: React.ReactNode;
}

export default function AppShell({ children }: Props) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden>CB</span>
          <span className="brand-text">
            <strong>Code-Buddy</strong>
            <small>Developer Intelligence</small>
          </span>
        </Link>
        <nav className="app-header-nav">
          <a href="https://github.com/Kunalp02/Code-Buddy" target="_blank" rel="noreferrer" className="header-link">
            Documentation
          </a>
        </nav>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <span>Local-first codebase intelligence for your organization</span>
      </footer>
    </div>
  );
}
