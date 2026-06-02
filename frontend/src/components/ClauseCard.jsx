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
    analysis_status,
    error_message,
    retrieved_benchmarks,
    cited_benchmark_ids,
    risk_rule_applied,
    evidence_summary,
    benchmark_alignment,
  } = clause;
  const isFailed = analysis_status === 'failed';
  const alignmentStyles = {
    strong: 'bg-green-50 text-green-700 border-green-200',
    partial: 'bg-blue-50 text-blue-700 border-blue-200',
    weak: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    none: 'bg-gray-50 text-gray-700 border-gray-200',
  };
  const safeAlignment = alignmentStyles[benchmark_alignment] ? benchmark_alignment : 'none';

  return (
    <div className="border rounded-lg overflow-hidden bg-white shadow-sm hover:shadow-md transition-shadow">
      {/* Header - Always visible */}
      <div
        className="p-4 flex items-center justify-between cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center space-x-3">
          <RiskBadge level={risk_level} />
          {isFailed && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border bg-red-50 text-red-700 border-red-200">
              Analysis Failed
            </span>
          )}
          {!isFailed && benchmark_alignment && (
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${alignmentStyles[safeAlignment]}`}>
              RAG {safeAlignment}
            </span>
          )}
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
            {error_message && (
              <p className="text-sm text-orange-800 mt-2">
                <span className="font-semibold">Error: </span>
                {error_message}
              </p>
            )}
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

          {(risk_rule_applied || evidence_summary || cited_benchmark_ids?.length > 0) && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">RAG Evidence</h4>
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 space-y-2">
                {risk_rule_applied && (
                  <p className="text-sm text-blue-900">
                    <span className="font-semibold">Rule: </span>
                    {risk_rule_applied}
                  </p>
                )}
                {evidence_summary && (
                  <p className="text-sm text-blue-900">
                    <span className="font-semibold">Evidence: </span>
                    {evidence_summary}
                  </p>
                )}
                {cited_benchmark_ids?.length > 0 && (
                  <p className="text-xs text-blue-800">
                    <span className="font-semibold">Cited: </span>
                    {cited_benchmark_ids.join(', ')}
                  </p>
                )}
              </div>
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

          {retrieved_benchmarks && retrieved_benchmarks.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Retrieved Benchmarks</h4>
              <div className="space-y-2">
                {retrieved_benchmarks.slice(0, 3).map((benchmark, index) => (
                  <div key={benchmark.id || index} className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-blue-900">
                      {benchmark.benchmark_id || benchmark.id || `Benchmark ${index + 1}`} - {benchmark.contract_type || 'unknown'} / {benchmark.clause_type || 'unknown'} / {benchmark.risk_level || 'unknown'} - similarity {benchmark.similarity ?? 'n/a'}
                    </p>
                    {(benchmark.risk_rule || benchmark.risk_notes) && (
                      <p className="text-xs text-blue-800 mt-1">{benchmark.risk_rule || benchmark.risk_notes}</p>
                    )}
                    {benchmark.why_risky && (
                      <p className="text-xs text-blue-700 mt-1">{benchmark.why_risky}</p>
                    )}
                    {benchmark.source_name && (
                      <p className="text-[11px] text-blue-700 mt-2">
                        Source: {benchmark.source_name}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ClauseCard;
