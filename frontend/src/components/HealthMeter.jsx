import React, { useEffect, useState } from 'react';

const HealthMeter = ({ score = 0, grade = 'N/A', label = 'Unknown', size = 280 }) => {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    const duration = 1200;
    const steps = 40;
    const safeScore = Number.isFinite(score) ? score : 0;
    const increment = safeScore / steps;
    let current = 0;
    let step = 0;

    const timer = setInterval(() => {
      step += 1;
      current = Math.min(safeScore, increment * step);
      setAnimatedScore(Math.round(current));
      if (step >= steps) {
        clearInterval(timer);
        setAnimatedScore(safeScore);
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [score]);

  const getColor = (s) => {
    if (s < 50) return '#ef4444';
    if (s < 75) return '#eab308';
    return '#22c55e';
  };

  const color = getColor(score);
  const displayGrade = grade || 'N/A';
  const displayLabel = label || 'Unknown';
  const boundedScore = Math.max(0, Math.min(animatedScore, 100));

  // SVG dimensions
  const viewW = 240;
  const viewH = 140;
  const cx = viewW / 2;
  const cy = viewH - 10;
  const r = 90;
  const strokeW = 20;

  // Arc path: semi-circle from left to right
  const arcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;

  // Needle angle: -180 (0) to 0 (100)
  const angle = -180 + (boundedScore / 100) * 180;
  const rad = (angle * Math.PI) / 180;
  const needleLen = r - 10;
  const nx = cx + needleLen * Math.cos(rad);
  const ny = cy + needleLen * Math.sin(rad);

  return (
    <div
      className="relative flex flex-col items-center justify-center"
      style={{ width: size, maxWidth: '100%' }}
    >
      <svg
        viewBox={`0 0 ${viewW} ${viewH}`}
        className="w-full h-auto"
        aria-label={`Health score ${score}, grade ${displayGrade}, ${displayLabel}`}
        role="img"
      >
        {/* Background track */}
        <path
          d={arcPath}
          fill="none"
          stroke="#e5e7eb"
          strokeLinecap="round"
          strokeWidth={strokeW}
        />
        {/* Progress arc */}
        <path
          d={arcPath}
          fill="none"
          pathLength="100"
          stroke={color}
          strokeDasharray={`${boundedScore} 100`}
          strokeLinecap="round"
          strokeWidth={strokeW}
        />
        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={nx}
          y2={ny}
          stroke="#374151"
          strokeWidth={3}
          strokeLinecap="round"
        />
        {/* Center pivot */}
        <circle cx={cx} cy={cy} r={5} fill="#374151" />
      </svg>

      {/* Text below gauge to avoid overlap */}
      <div className="flex flex-col items-center mt-2">
        <span className="text-3xl font-bold" style={{ color }}>
          {animatedScore}
        </span>
        <span className="text-lg font-semibold" style={{ color }}>
          Grade {displayGrade}
        </span>
        <span className="text-sm font-medium text-gray-500">
          {displayLabel}
        </span>
      </div>
    </div>
  );
};

export default HealthMeter;
