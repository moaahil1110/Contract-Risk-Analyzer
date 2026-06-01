import React, { useEffect, useState } from 'react';

const HealthMeter = ({ score = 0, grade = 'N/A', label = 'Unknown', size = 300 }) => {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    // Animate the score on load
    const duration = 1500;
    const steps = 60;
    const safeScore = Number.isFinite(score) ? score : 0;
    const increment = safeScore / steps;
    let current = 0;

    const timer = setInterval(() => {
      current += increment;
      if (current >= safeScore) {
        setAnimatedScore(safeScore);
        clearInterval(timer);
      } else {
        setAnimatedScore(Math.round(current));
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [score]);

  // Determine color and grade based on score
  const getColor = (s) => {
    if (s < 50) return '#ef4444'; // red
    if (s < 75) return '#eab308'; // yellow
    return '#22c55e'; // green
  };

  const color = getColor(score);
  const displayGrade = grade || 'N/A';
  const displayLabel = label || 'Unknown';
  const boundedScore = Math.max(0, Math.min(animatedScore, 100));

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, maxWidth: '100%', aspectRatio: '1.6 / 1' }}
    >
      <svg
        viewBox="0 0 240 150"
        className="h-full w-full overflow-visible"
        aria-label={`Health score ${score}, grade ${displayGrade}, ${displayLabel}`}
        role="img"
      >
        <path
          d="M 30 118 A 90 90 0 0 1 210 118"
          fill="none"
          stroke="#e5e7eb"
          strokeLinecap="round"
          strokeWidth="22"
        />
        <path
          d="M 30 118 A 90 90 0 0 1 210 118"
          fill="none"
          pathLength="100"
          stroke={color}
          strokeDasharray={`${boundedScore} 100`}
          strokeLinecap="round"
          strokeWidth="22"
        />
        <text
          x="120"
          y="78"
          fill={color}
          fontSize="44"
          fontWeight="700"
          textAnchor="middle"
        >
          {animatedScore}
        </text>
        <text
          x="120"
          y="108"
          fill={color}
          fontSize="24"
          fontWeight="700"
          textAnchor="middle"
        >
          {displayGrade}
        </text>
        <text
          x="120"
          y="135"
          fill="#6b7280"
          fontSize="16"
          fontWeight="500"
          textAnchor="middle"
        >
          {displayLabel}
        </text>
      </svg>
    </div>
  );
};

export default HealthMeter;
