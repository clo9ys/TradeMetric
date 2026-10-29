import type { SVGProps } from 'react';
type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{children}</svg>;
}
export function ChartIcon() {
  return <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M2 14h8v13H2zM10 4h8v23h-8zM18 10h8v17h-8z" stroke="currentColor" strokeWidth="2.7" strokeLinejoin="round" /></svg>;
}
export function DocumentIcon() { return <Icon><path d="M7 3h7l5 5v12H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M13 3v6h6" /></Icon>; }
export function UserIcon() { return <Icon><circle cx="12" cy="7" r="4.5" /><path d="M4 22v-1c0-4 3.6-6 8-6s8 2 8 6v1" /></Icon>; }
export function ChevronIcon() { return <Icon><path d="m7 10 5 5 5-5" /></Icon>; }
export function PlusIcon() { return <Icon><path d="M12 4v16M4 12h16" /></Icon>; }
export function ArrowIcon() { return <Icon><path d="M3 12h18m-6-6 6 6-6 6" /></Icon>; }
export function TrashIcon() { return <Icon><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></Icon>; }
export function InfoIcon() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.01" /></Icon>; }
