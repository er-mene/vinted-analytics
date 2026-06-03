import { Link, useLocation } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/queue", label: "Queue" },
];

export default function Navbar() {
  const { pathname } = useLocation();

  return (
    <nav className="flex items-center gap-6 px-6 py-4 border-b border-line">
      <span className="mr-auto text-accent font-serif text-lg font-bold">
        Vinted Analytics
      </span>
      {links.map(({ to, label }) => (
        <Link
          key={to}
          to={to}
          className={
            "font-sans text-sm no-underline transition-colors " +
            (pathname === to
              ? "text-ink font-semibold"
              : "text-muted hover:text-ink")
          }
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
