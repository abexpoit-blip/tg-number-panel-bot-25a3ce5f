import { NavLink, useNavigate } from "react-router-dom";
import { Zap, LayoutDashboard, Radio, Phone, Layers, Globe, Users, Wallet, Settings as SettingsIcon, LogOut, Plug, Sparkles, Hash, Megaphone } from "lucide-react";
import { setToken } from "@/lib/api";

const LINKS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/otp", label: "Live OTP", icon: Radio },
  { to: "/feed", label: "Feed Channels", icon: Megaphone },
  { to: "/numbers", label: "Numbers", icon: Phone },
  { to: "/services", label: "Services", icon: Layers },
  { to: "/providers", label: "Providers", icon: Plug },
  { to: "/countries", label: "Countries", icon: Globe },
  { to: "/ranges", label: "Ranges", icon: Hash },
  { to: "/emoji-preview", label: "Emoji Preview", icon: Sparkles },
  { to: "/users", label: "Users", icon: Users },
  { to: "/withdrawals", label: "Withdrawals", icon: Wallet },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function Sidebar() {
  const nav = useNavigate();
  const logout = () => { setToken(null); nav("/login"); };

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/80 backdrop-blur-2xl relative">
      {/* glow stripe */}
      <div className="absolute right-0 top-0 h-full w-px bg-gradient-to-b from-transparent via-primary/30 to-transparent" />

      <div className="flex items-center gap-3 px-6 py-6">
        <div className="relative">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-primary shadow-glow">
            <Zap className="h-5 w-5 text-primary-foreground" strokeWidth={2.5} />
          </div>
          <div className="absolute inset-0 rounded-xl bg-gradient-primary blur-xl opacity-50 -z-10" />
        </div>
        <div>
          <div className="font-display text-lg font-bold tracking-tight text-sidebar-accent-foreground">Seven1tel</div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-sidebar-foreground/50 font-medium">Admin Panel</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {LINKS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <button
          onClick={logout}
          className="nav-link w-full hover:!bg-destructive/15 hover:!text-destructive"
        >
          <LogOut className="h-4 w-4" /> Logout
        </button>
      </div>
    </aside>
  );
}
