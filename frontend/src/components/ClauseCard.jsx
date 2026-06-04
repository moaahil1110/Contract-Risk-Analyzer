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
    provider_used,
    retry_count,
    predicted_clause_type,
    clause_type_confidence,
    retrieval_quality,
    eligible_benchmark_count,
    citation_suppressed,
    clause_number,
    subclauses,
    parsed_section_count,
  } = clause;

  const isFailed = analysis_status === 'failed';

  const riskChipClass = {
    high: 'bg-red-50 text-red-700 border-red-200',
    medium: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    low: 'bg-green-50 text-green-700 border-green-200',
    unknown: 'bg-gray-100 text-gray-700 border-gray-200',
  };

  const statusChipClass = {
    success: 'bg-blue-50 text-blue-700 border-blue-200',
    retried: 'bg-orange-50 text-orange-700 border-orange-200',
    failed: 'bg-red-50 text-red-700 border-red-200',
  };

  const riskLabels = {
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    unknown: 'Unknown',
  };

  const statusLabels = {
    success: 'Success',
    retried: 'Retried',
    failed: 'Failed',
  };

  const alignmentChipClass = {
    strong: 'bg-green-50 text-green-700 border-green-200',
    partial: 'bg-blue-50 text-blue-700 border-blue-200',
    weak: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    none: 'bg-gray-100 text-gray-600 border-gray-200',
  };

  const safeRisk = riskChipClass[risk_level] ? risk_level : 'unknown';
  const safeStatus = statusChipClass[analysis_status] ? analysis_status : 'success';
  const safeAlignment = alignmentChipClass[benchmark_alignment] ? benchmark_alignment : 'none';

  return (
    <div className="border rounded-lg overflow-hidden bg-white shadow-sm hover:shadow-md transition-shadow">
      {/* Header - Always visible */}
      <div
        className="p-4 flex items-center justify-between cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3 flex-wrap">
          <RiskBadge level={risk_level} />
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${riskChipClass[safeRisk]}`}>
              {riskLabels[safeRisk]}
            </span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${statusChipClass[safeStatus]}`}>
              {statusLabels[safeStatus]}
            </span>
            {provider_used && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-gray-50 text-gray-600 border-gray-200">
                {provider_used}
              </span>
            )}
            {typeof retry_count === 'number' && retry_count > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-orange-50 text-orange-700 border-orange-200">
                Retries: {retry_count}
              </span>
            )}
            {!isFailed && (
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${alignmentChipClass[safeAlignment]}`}>
                RAG {safeAlignment}
              </span>
            )}
            {predicted_clause_type && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-indigo-50 text-indigo-700 border-indigo-200">
                {predicted_clause_type}
              </span>
            )}
            {retrieval_quality && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-gray-50 text-gray-600 border-gray-200">
                Retrieval {retrieval_quality}
              </span>
            )}
            {clause_number && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-slate-50 text-slate-700 border-slate-200">
                Clause {clause_number}
              </span>
            )}
            {parsed_section_count > 1 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-slate-50 text-slate-700 border-slate-200">
                {parsed_section_count} sections
              </span>
            )}
          </div>
          <h3 className="font-semibold text-gray-900 text-sm sm:text-base">{clause_title}</h3>
        </div>
        <button className="p-1 hover:bg-gray-200 rounded-full transition-colors flex-shrink-0">
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

          {subclauses && subclauses.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Nested Sections</h4>
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                <ul className="space-y-1">
                  {subclauses.slice(0, 12).map((subclause, index) => (
                    <li key={`${subclause.clause_number || index}`} className="text-xs text-slate-700">
                      <span className="font-semibold">{subclause.clause_number}</span>
                      {subclause.heading ? ` ${subclause.heading}` : ` ${subclause.section_type || 'Subclause'}`}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

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

          {/* RAG Evidence */}
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
                {citation_suppressed && (
                  <p className="text-xs text-blue-800">
                    <span className="font-semibold">Benchmark Match: </span>
                    No strong benchmark match found; weak retrievals are diagnostic only.
                  </p>
                )}
                <p className="text-xs text-blue-800">
                  <span className="font-semibold">Eligible Benchmarks: </span>
                  {eligible_benchmark_count || 0}
                  {predicted_clause_type && (
                    <span> · Predicted type: {predicted_clause_type} ({Math.round((clause_type_confidence || 0) * 100)}%)</span>
                  )}
                </p>
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

          {/* Retrieved Benchmarks */}
          {retrieved_benchmarks && retrieved_benchmarks.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Retrieved Benchmarks</h4>
              <div className="space-y-2">
                {retrieved_benchmarks.slice(0, 3).map((benchmark, index) => (
                  <div key={benchmark.id || index} className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-blue-900">
                      {benchmark.benchmark_id || benchmark.id || `Benchmark ${index + 1}`} — {benchmark.contract_type || 'unknown'} / {benchmark.clause_type || 'unknown'} / {benchmark.risk_level || 'unknown'} — similarity {benchmark.similarity ?? 'n/a'} — eligible {benchmark.citation_eligible ? 'yes' : 'no'}
                    </p>
                    {benchmark.relevance_reason && (
                      <p className="text-[11px] text-blue-700 mt-1">Reason: {benchmark.relevance_reason}</p>
                    )}
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
