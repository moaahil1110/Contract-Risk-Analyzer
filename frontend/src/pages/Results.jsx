import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getCurrentUser } from '../lib/supabase';
import { getAnalysis, exportReport } from '../lib/api';
import HealthMeter from '../components/HealthMeter';
import ClauseCard from '../components/ClauseCard';
import RiskBadge from '../components/RiskBadge';
import { 
  Shield, 
  ArrowLeft, 
  Download, 
  FileText,
  Loader2,
  AlertCircle,
  Filter
} from 'lucide-react';

const Results = () => {
  const navigate = useNavigate();
  const { contractId } = useParams();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // 'all', 'high', 'medium', 'low'
  const [exporting, setExporting] = useState(false);

  const filters = [
    { value: 'all', label: 'All Clauses' },
    { value: 'high', label: 'High Risk Only' },
    { value: 'medium', label: 'Medium Risk Only' },
    { value: 'low', label: 'Low Risk Only' },
  ];

  useEffect(() => {
    checkAuth();
    loadAnalysis();
  }, [contractId]);

  const checkAuth = async () => {
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
      const blob = await exportReport(contractId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `risk-report-${analysis?.filename || 'contract'}.pdf`;
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
    if (filter === 'all') return true;
    return clause.risk_level?.toLowerCase() === filter;
  }) || [];

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

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Contract Info */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-2">
            <FileText className="w-6 h-6 text-gray-400" />
            <h1 className="text-2xl font-bold text-gray-900">{analysis?.filename}</h1>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-gray-600 capitalize">
              Type: {analysis?.contract_type}
            </span>
            {analysis?.health && (
              <RiskBadge level={analysis.health.risk_counts?.high > 0 ? 'high' : analysis.health.risk_counts?.medium > 0 ? 'medium' : 'low'} />
            )}
          </div>
        </div>

        {/* Health Score Section */}
        {analysis?.health && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-8">
            <div className="flex flex-col md:flex-row items-center justify-center gap-8">
              {/* Health Meter */}
              <div className="flex-shrink-0">
                <HealthMeter score={analysis.health.score} size={280} />
              </div>

              {/* Summary Stats */}
              <div className="flex-1 max-w-md">
                <h2 className="text-xl font-semibold text-gray-900 mb-4">Risk Summary</h2>
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-red-50 rounded-lg p-4 text-center">
                    <p className="text-3xl font-bold text-red-600">
                      {analysis.health.risk_counts?.high || 0}
                    </p>
                    <p className="text-sm text-red-700 mt-1">High Risk</p>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-4 text-center">
                    <p className="text-3xl font-bold text-yellow-600">
                      {analysis.health.risk_counts?.medium || 0}
                    </p>
                    <p className="text-sm text-yellow-700 mt-1">Medium Risk</p>
                  </div>
                  <div className="bg-green-50 rounded-lg p-4 text-center">
                    <p className="text-3xl font-bold text-green-600">
                      {analysis.health.risk_counts?.low || 0}
                    </p>
                    <p className="text-sm text-green-700 mt-1">Low Risk</p>
                  </div>
                </div>
                <p className="text-center text-gray-500 mt-4">
                  Total: {analysis.health.total_clauses || 0} clauses analyzed
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Filter Bar */}
        <div className="mb-6">
          <div className="flex items-center space-x-2 overflow-x-auto pb-2">
            <Filter className="w-4 h-4 text-gray-500 flex-shrink-0" />
            {filters.map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                  filter === f.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Clauses List */}
        <div className="space-y-4">
          {filteredClauses.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <p className="text-gray-500">No clauses match the selected filter</p>
            </div>
          ) : (
            filteredClauses.map((clause) => (
              <ClauseCard key={clause.id} clause={clause} />
            ))
          )}
        </div>
      </main>
    </div>
  );
};

export default Results;
