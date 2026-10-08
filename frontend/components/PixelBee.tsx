export function PixelBee({ className = "", animate = true }: { className?: string; animate?: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      shapeRendering="crispEdges"
      className={`${animate ? "buzzing" : ""} ${className}`}
      width="40"
      height="40"
    >
      {/* wings */}
      <rect x="2" y="3" width="3" height="3" fill="#f3e9d2" opacity="0.85" />
      <rect x="11" y="3" width="3" height="3" fill="#f3e9d2" opacity="0.85" />
      {/* body stripes */}
      <rect x="5" y="4" width="6" height="2" fill="#0d0a14" />
      <rect x="5" y="6" width="6" height="2" fill="#ffc93c" />
      <rect x="5" y="8" width="6" height="2" fill="#0d0a14" />
      <rect x="5" y="10" width="6" height="2" fill="#ffc93c" />
      {/* head */}
      <rect x="6" y="2" width="4" height="2" fill="#0d0a14" />
      {/* eyes */}
      <rect x="6" y="2" width="1" height="1" fill="#ffffff" />
      <rect x="9" y="2" width="1" height="1" fill="#ffffff" />
      {/* stinger */}
      <rect x="7" y="12" width="2" height="1" fill="#0d0a14" />
    </svg>
  );
}
