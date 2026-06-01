import React from 'react';

const RiskBadge = ({ level, className = '' }) => {
  const styles = {
    high: 'bg-red-100 text-red-700 border-red-200',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    low: 'bg-green-100 text-green-700 border-green-200',
  };

  const labels = {
    high: 'High Risk',
    medium: 'Medium Risk',
    low: 'Low Risk',
  };

  const normalizedLevel = level?.toLowerCase() || 'medium';

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[normalizedLevel]} ${className}`}
    >
      {labels[normalizedLevel]}
    </span>
  );
};

export default RiskBadge;
