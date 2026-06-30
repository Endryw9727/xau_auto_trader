import { ShieldOff } from "lucide-react";

export default function SafetyBanner() {
  return (
    <div
      data-testid="safety-banner"
      className="flex items-center justify-center gap-2 bg-warn text-black font-mono text-[11px] sm:text-xs font-semibold tracking-wider px-3 py-1 select-none"
    >
      <ShieldOff size={13} strokeWidth={2} className="shrink-0" />
      <span className="animate-blink">●</span>
      LIVE DISARMED · READ-ONLY RESEARCH · allow_real_live = false · NO REAL ORDERS
    </div>
  );
}
