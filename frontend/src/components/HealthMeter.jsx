import React, { useEffect, useState } from 'react';
import { RadialBarChart, RadialBar, ResponsiveContainer, Cell } from 'recharts';

const HealthMeter = ({ score, size = 300 }) => {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    // Animate the score on load
    const duration = 1500;
    const steps = 60;
    const increment = score / steps;
    let current = 0;

    const timer = setInterval(() => {
      current += increment;
      if (current >= score) {
        setAnimatedScore(score);
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

  const getGrade = (s) => {
    if (s >= 80) return { grade: 'A', label: 'Low Risk' };
    if (s >= 60) return { grade: 'B', label: 'Moderate Risk' };
    if (s >= 40) return { grade: 'C', label: 'High Risk' };
    return { grade: 'D', label: 'Critical Risk' };
  };

  const color = getColor(score);
  const { grade, label } = getGrade(score);

  // Data for the radial chart
  const data = [
    {
      name: 'Score',
      value: score,
      fill: color,
    },
  ];

  return (
    <div className="flex flex-col items-center" style={{ width: size, height: size * 1.2 }}>
      <ResponsiveContainer width="100%" height="80%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="60%"
          outerRadius="90%"
          barSize={20}
          data={data}
          startAngle={180}
          endAngle={0}
        >
          <RadialBar
            minAngle={15}
            background
            clockWise
            dataKey="value"
            cornerRadius={10}
          >
            <Cell fill={color} />
          </RadialBar>
        </RadialBarChart>
      </ResponsiveContainer>

      {/* Center text overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" style={{ marginTop: '-20px' }}>
        <div className="text-center">
          <span
            className="text-6xl font-bold"
            style={{ color }}
          >
            {animatedScore}
          </span>
          <div className="text-2xl font-semibold mt-2" style={{ color }}>
            {grade}
          </div>
          <div className="text-sm text-gray-500 mt-1">{label}</div>
        </div>
      </div>

      {/* Background circle for empty portion */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div
          className="rounded-full"
          style={{
            width: size * 0.55,
            height: size * 0.55,
            border: `8px solid #f3f4f6`,
          }}
        />
      </div>
    </div>
  );
};

export default HealthMeter;
