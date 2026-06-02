import React from 'react';

const RiskBadge = ({ level, className = '' }) => {
  const styles = {
    high: 'bg-red-100 text-red-700 border-red-200',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    low: 'bg-green-100 text-green-700 border-green-200',
    unknown: 'bg-gray-100 text-gray-700 border-gray-200',
  };

  const labels = {
    high: 'High Risk',
    medium: 'Medium Risk',
    low: 'Low Risk',
    unknown: 'Unknown',
  };

  const normalizedLevel = level?.toLowerCase() || 'unknown';
  const safeLevel = styles[normalizedLevel] ? normalizedLevel : 'unknown';

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[safeLevel]} ${className}`}
    >
      {labels[safeLevel]}
    </span>
  );
};

export default RiskBadge;
