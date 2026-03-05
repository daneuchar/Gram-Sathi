import {
  LayoutDashboard,
  Radio,
  PhoneCall,
  Users,
  BarChart3,
  Activity,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Live Monitor", href: "/live-monitor", icon: Radio },
  { label: "Call History", href: "/call-history", icon: PhoneCall },
  { label: "User Profiles", href: "/user-profiles", icon: Users },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "System Health", href: "/system-health", icon: Activity },
];

export function getPageTitle(pathname: string): string {
  const item = NAV_ITEMS.find((n) => n.href === pathname);
  return item?.label ?? "Dashboard";
}
