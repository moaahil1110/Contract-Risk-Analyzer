import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getCurrentUser } from '../lib/supabase';
import { getAnalysis, exportReport } from '../lib/api';
import HealthMeter from '../components/HealthMeter';
import ClauseCard from '../components/ClauseCard';
import {
  Shield,
  ArrowLeft,
  Download,
  FileText,
  Loader2,
  AlertCircle,
  AlertTriangle,
  Filter,
  Search,
} from 'lucide-react';

const CI_BYPASS_AUTH = import.meta.env.VITE_CI_BYPASS_AUTH === 'true';

const Results = () => {
  const navigate = useNavigate();
  const { contractId } = useParams();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [exporting, setExporting] = useState(false);

  const filters = [
    { value: 'all', label: 'All Clauses' },
    { value: 'high', label: 'High Risk' },
    { value: 'medium', label: 'Medium Risk' },
    { value: 'low', label: 'Low Risk' },
    { value: 'unknown', label: 'Unknown' },
    { value: 'failed', label: 'Failed' },
  ];

  useEffect(() => {
    checkAuth();
    loadAnalysis();
  }, [contractId]);

  const checkAuth = async () => {
    if (CI_BYPASS_AUTH) return;
    const user = await getCurrentUser();
    if (!user) {
      navigate('/login');
    }
  };

  const loadAnalysis = async () => {
    try {
      setLoading(true);
      const data = await getAnalysis(contractId);
      setAnalysis(data);
    } catch (err) {
      setError(err.message || 'Failed to load analysis');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const { blob, filename } = await exportReport(contractId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `risk-report-${(analysis?.filename || 'contract').replace(/\.pdf$/i, '')}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || 'Failed to export report');
    } finally {
      setExporting(false);
    }
  };

  const filteredClauses = analysis?.clauses?.filter((clause) => {
    const matchesFilter =
      filter === 'all'
        ? true
        : filter === 'failed'
        ? clause.analysis_status === 'failed'
        : clause.risk_level?.toLowerCase() === filter;
    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      !q ||
      clause.clause_title?.toLowerCase().includes(q) ||
      clause.original_text?.toLowerCase().includes(q) ||
      clause.plain_english?.toLowerCase().includes(q);
    return matchesFilter && matchesSearch;
  }) || [];

  const failedClauses = analysis?.clauses?.filter((c) => c.analysis_status === 'failed') || [];
  const topRiskyClauses = (analysis?.clauses || [])
    .filter((c) => ['high', 'medium'].includes(c.risk_level?.toLowerCase()) && c.analysis_status !== 'failed')
    .sort((a, b) => {
      const aHigh = a.risk_level === 'high' ? 1 : 0;
      const bHigh = b.risk_level === 'high' ? 1 : 0;
      if (aHigh !== bHigh) return bHigh - aHigh;
      return (b.risk_score || 0) - (a.risk_score || 0);
    })
    .slice(0, 5);

  const health = analysis?.health || {};
  const failedClauseCount = health.failed_clause_count || 0;
  const unknownCount = health.unknown_count || 0;
  const topLevelClauseCount = health.top_level_clause_count || health.total_clauses || analysis?.top_level_clause_count || 0;
  const parsedSectionCount = health.parsed_section_count || analysis?.parsed_section_count || topLevelClauseCount;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600 mb-4" />
          <p className="text-gray-600">Loading analysis results...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="text-center max-w-md">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Error Loading Results</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/')}
              className="flex items-center text-gray-600 hover:text-gray-900 transition-colors"
            >
              <ArrowLeft className="w-5 h-5 mr-1" />
              <span className="font-medium">Back</span>
            </button>
            <div className="h-6 w-px bg-gray-300" />
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <Shield className="w-4 h-4 text-white" />
              </div>
              <h1 className="text-lg font-bold text-gray-900 hidden sm:block">Contract Risk Analyzer</h1>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors"
            >
              {exporting ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Download className="w-4 h-4 mr-2" />
              )}
              <span className="hidden sm:inline">Export Report</span>
            </button>
            <button
              onClick={() => navigate('/')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Analyze Another
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Contract Info */}
        <div>
          <div className="flex items-center space-x-3 mb-2">
            <FileText className="w-6 h-6 text-gray-400" />
            <h1 className="text-2xl font-bold text-gray-900">{analysis?.filename}</h1>
          </div>
          <div className="flex items-center space-x-4 flex-wrap gap-y-2">
            <span className="text-gray-600 capitalize">
              Type: {analysis?.contract_type}
            </span>
            {analysis?.health && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border bg-gray-100 text-gray-700 border-gray-200">
                {analysis.health.grade} — {analysis.health.label}
              </span>
            )}
          </div>
          {analysis?.contract_type_conflict && (
            <div className="mt-3 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              Selected type was {analysis.selected_contract_type}, but the document looks like {analysis.detected_contract_type}.
              The analysis used {analysis.contract_type}.
            </div>
          )}
          {analysis?.warning && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              <span>{analysis.warning}</span>
            </div>
          )}
        </div>

        {/* Overall Score */}
        {analysis?.health && (
          <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Overall Score</h2>
            {failedClauseCount > 0 && (
              <div className="mb-6 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" />
                <div>
                  <p className="font-semibold">{failedClauseCount} clause(s) failed analysis</p>
                  <p className="text-sm">Failed clauses are marked Unknown and excluded from the health score.</p>
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] items-start gap-6 lg:gap-10">
              <div className="w-full max-w-[280px] mx-auto lg:mx-0">
                <HealthMeter
                  score={analysis.health.score}
                  grade={analysis.health.grade}
                  label={analysis.health.label}
                  size={280}
                />
              </div>
              <div className="w-full">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Risk Breakdown</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                  <div className="bg-red-50 rounded-lg p-3 text-center border border-red-100">
                    <p className="text-2xl font-bold text-red-600">{analysis.health.risk_counts?.high || 0}</p>
                    <p className="text-xs text-red-700 mt-1">High Risk</p>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-3 text-center border border-yellow-100">
                    <p className="text-2xl font-bold text-yellow-600">{analysis.health.risk_counts?.medium || 0}</p>
                    <p className="text-xs text-yellow-700 mt-1">Medium Risk</p>
                  </div>
                  <div className="bg-green-50 rounded-lg p-3 text-center border border-green-100">
                    <p className="text-2xl font-bold text-green-600">{analysis.health.risk_counts?.low || 0}</p>
                    <p className="text-xs text-green-700 mt-1">Low Risk</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 text-center border border-gray-200">
                    <p className="text-2xl font-bold text-gray-600">{unknownCount}</p>
                    <p className="text-xs text-gray-700 mt-1">Unknown</p>
                  </div>
                  <div className="bg-red-50 rounded-lg p-3 text-center border border-red-100">
                    <p className="text-2xl font-bold text-red-600">{failedClauseCount}</p>
                    <p className="text-xs text-red-700 mt-1">Failed</p>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3 text-center border border-blue-100">
                    <p className="text-2xl font-bold text-blue-600">{analysis.health.scored_clause_count || 0}</p>
                    <p className="text-xs text-blue-700 mt-1">Scored</p>
                  </div>
                </div>
                <p className="text-center text-gray-500 mt-3 text-sm">
                  {topLevelClauseCount} top-level clauses analyzed from {parsedSectionCount} parsed sections
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Top Risky Clauses */}
        {topRiskyClauses.length > 0 && (
          <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Top Risky Clauses</h2>
            <div className="space-y-3">
              {topRiskyClauses.map((clause) => (
                <ClauseCard key={clause.id || clause.clause_index} clause={clause} />
              ))}
            </div>
          </section>
        )}

        {/* Failed Analysis */}
        {failedClauses.length > 0 && (
          <section className="bg-white rounded-xl shadow-sm border border-red-200 p-5 sm:p-6">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <h2 className="text-lg font-semibold text-gray-900">Failed Analysis</h2>
              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                {failedClauses.length}
              </span>
            </div>
            <div className="space-y-3">
              {failedClauses.map((clause) => (
                <ClauseCard key={clause.id || clause.clause_index} clause={clause} />
              ))}
            </div>
          </section>
        )}

        {/* Full Clause Analysis */}
        <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Full Clause Analysis</h2>

          {/* Filters */}
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            <div className="flex items-center space-x-2 overflow-x-auto pb-2">
              <Filter className="w-4 h-4 text-gray-500 flex-shrink-0" />
              {filters.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setFilter(f.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                    filter === f.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search clauses..."
                className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
          </div>

          {/* Clauses List */}
          <div className="space-y-4">
            {filteredClauses.length === 0 ? (
              <div className="text-center py-12 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-gray-500">No clauses match the selected filter</p>
              </div>
            ) : (
              filteredClauses.map((clause) => (
                <ClauseCard key={clause.id || clause.clause_index} clause={clause} />
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
};

export default Results;
