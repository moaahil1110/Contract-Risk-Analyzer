import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import RiskBadge from './RiskBadge';

const ClauseCard = ({ clause }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const {
    clause_title,
    original_text,
    risk_level,
    risk_reason,
    plain_english,
    key_concerns,
    suggested_fix,
  } = clause;

  return (
    <div className="border rounded-lg overflow-hidden bg-white shadow-sm hover:shadow-md transition-shadow">
      {/* Header - Always visible */}
      <div
        className="p-4 flex items-center justify-between cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center space-x-3">
          <RiskBadge level={risk_level} />
          <h3 className="font-semibold text-gray-900">{clause_title}</h3>
        </div>
        <button className="p-1 hover:bg-gray-200 rounded-full transition-colors">
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-gray-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-500" />
          )}
        </button>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="p-4 border-t border-gray-200 space-y-4">
          {/* Risk Reason */}
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
            <p className="text-sm text-orange-800">
              <span className="font-semibold">Risk: </span>
              {risk_reason}
            </p>
          </div>

          {/* Original Text */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Original Clause</h4>
            <div className="bg-gray-100 border border-gray-300 rounded-lg p-3 max-h-40 overflow-y-auto">
              <p className="text-sm text-gray-700 font-mono whitespace-pre-wrap">
                {original_text}
              </p>
            </div>
          </div>

          {/* Plain English */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">What This Means</h4>
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <p className="text-sm text-gray-800 leading-relaxed">{plain_english}</p>
            </div>
          </div>

          {/* Key Concerns */}
          {key_concerns && key_concerns.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Key Concerns</h4>
              <ul className="space-y-2">
                {key_concerns.map((concern, index) => (
                  <li key={index} className="flex items-start space-x-2">
                    <span className="text-red-500 mt-1">•</span>
                    <span className="text-sm text-gray-700">{concern}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested Fix */}
          {suggested_fix && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Suggested Fix</h4>
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-sm text-gray-800 italic">{suggested_fix}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ClauseCard;
