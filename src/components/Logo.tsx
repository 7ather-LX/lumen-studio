export function Logo({ size = 30, glow = true }: { size?: number; glow?: boolean }) {
  return (
    <span className={glow ? "logo logo-glow" : "logo"} style={{ width: size, height: size }}>
      <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
        <defs>
          <linearGradient id="lumen-logo-gradient" x1="8" y1="6" x2="42" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#E7FF9B" />
            <stop offset="0.5" stopColor="#C9F56D" />
            <stop offset="1" stopColor="#67D7C4" />
          </linearGradient>
        </defs>
        <circle cx="24" cy="24" r="9.5" fill="url(#lumen-logo-gradient)" />
        <path
          d="M24 5.5v7.2M24 35.3v7.2M5.5 24h7.2M35.3 24h7.2M11 11l5.1 5.1M31.9 31.9l5.1 5.1M37 11l-5.1 5.1M16.1 31.9 11 37"
          stroke="url(#lumen-logo-gradient)"
          strokeWidth="2.6"
          strokeLinecap="round"
          opacity="0.9"
        />
        <circle cx="24" cy="24" r="16.5" stroke="url(#lumen-logo-gradient)" strokeWidth="1.2" opacity="0.25" />
      </svg>
    </span>
  );
}
