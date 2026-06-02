import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadContract, startAnalysis, getHistory, pollUntilComplete, rerunAnalysis, deleteContract, exportReport } from '../lib/api';
import { signOut, getCurrentUser } from '../lib/supabase';
import UploadZone from '../components/UploadZone';
import RiskBadge from '../components/RiskBadge';
import {
  Shield,
  LogOut,
  FileText,
  Loader2,
  AlertCircle,
  ChevronRight,
  Clock,
  CheckCircle2,
  Eye,
  Download,
  RefreshCw,
  Trash2,
  Search,
  Filter,
  X,
} from 'lucide-react';

const progressStages = [
  { key: 'upload', label: 'Uploading PDF' },
  { key: 'queued', label: 'Queued' },
  { key: 'extract', label: 'Extracting clauses' },
  { key: 'retrieve', label: 'Retrieving benchmarks' },
  { key: 'analyse', label: 'Analyzing risks' },
  { key: 'save', label: 'Saving results' },
  { key: 'complete', label: 'Complete' },
];

const statusToStage = {
  uploaded: 'upload',
  queued: 'queued',
  extracting: 'extract',
  clauses_extracted: 'extract',
  retrieving_benchmarks: 'retrieve',
  analysing: 'analyse',
  saving_results: 'save',
  complete: 'complete',
};

const statusBadgeClass = {
  uploaded: 'bg-gray-100 text-gray-700 border-gray-200',
  queued: 'bg-blue-50 text-blue-700 border-blue-200',
  extracting: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  clauses_extracted: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  retrieving_benchmarks: 'bg-purple-50 text-purple-700 border-purple-200',
  analysing: 'bg-orange-50 text-orange-700 border-orange-200',
  saving_results: 'bg-teal-50 text-teal-700 border-teal-200',
  complete: 'bg-green-50 text-green-700 border-green-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [file, setFile] = useState(null);
  const [contractType, setContractType] = useState('nda');
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [contractId, setContractId] = useState(null);
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [currentStage, setCurrentStage] = useState(null);

  // History filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterGrade, setFilterGrade] = useState('');

  // Confirmations
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [confirmRerun, setConfirmRerun] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const contractTypes = [
    { value: 'nda', label: 'NDA (Non-Disclosure Agreement)' },
    { value: 'employment', label: 'Employment Contract' },
    { value: 'vendor', label: 'Vendor Agreement' },
    { value: 'other', label: 'Other' },
  ];

  const statusOptions = [
    { value: '', label: 'All Statuses' },
    { value: 'uploaded', label: 'Uploaded' },
    { value: 'queued', label: 'Queued' },
    { value: 'extracting', label: 'Extracting' },
    { value: 'clauses_extracted', label: 'Clauses Extracted' },
    { value: 'retrieving_benchmarks', label: 'Retrieving Benchmarks' },
    { value: 'analysing', label: 'Analysing' },
    { value: 'saving_results', label: 'Saving Results' },
    { value: 'complete', label: 'Complete' },
    { value: 'failed', label: 'Failed' },
  ];

  const gradeOptions = [
    { value: '', label: 'All Grades' },
    { value: 'A', label: 'A' },
    { value: 'B', label: 'B' },
    { value: 'C', label: 'C' },
    { value: 'D', label: 'D' },
    { value: 'F', label: 'F' },
    { value: 'N/A', label: 'N/A' },
  ];

  useEffect(() => {
    checkAuth();
    loadHistory();
  }, []);

  const checkAuth = async () => {
    const currentUser = await getCurrentUser();
    if (!currentUser) {
      navigate('/login');
      return;
    }
    setUser(currentUser);
  };

  const loadHistory = async (overrideFilters = null) => {
    try {
      setHistoryLoading(true);
      const filters = overrideFilters || {
        search: searchQuery,
        status: filterStatus,
        contract_type: filterType,
        grade: filterGrade,
      };
      const data = await getHistory({
        search: filters.search || undefined,
        status: filters.status || undefined,
        contract_type: filters.contract_type || undefined,
        grade: filters.grade || undefined,
      });
      setHistory(data.contracts || []);
    } catch (err) {
      console.error('Failed to load history:', err);
      const msg = err.message || '';
      if (msg.toLowerCase().includes('session') || msg.toLowerCase().includes('log in') || msg.toLowerCase().includes('auth')) {
        navigate('/login');
      }
    } finally {
      setHistoryLoading(false);
    }
  };

  const applyFilters = () => {
    loadHistory();
  };

  const clearFilters = () => {
    const cleared = { search: '', status: '', contract_type: '', grade: '' };
    setSearchQuery('');
    setFilterStatus('');
    setFilterType('');
    setFilterGrade('');
    loadHistory(cleared);
  };

  const handleFileSelect = (selectedFile) => {
    setFile(selectedFile);
    setError(null);
    setAnalysisStatus('');
    setCurrentStage(null);
    setContractId(null);
  };

  const handleAnalyze = async () => {
    if (!file) {
      setError('Please select a PDF file to analyze');
      return;
    }

    setLoading(true);
    setError(null);
    setCurrentStage('upload');
    setAnalysisStatus('Uploading PDF...');

    try {
      setAnalysisStatus('Uploading PDF...');
      const uploadResponse = await uploadContract(file, contractType);
      setContractId(uploadResponse.contract_id);
      setAnalyzing(true);
      setCurrentStage('queued');
      setAnalysisStatus('Starting analysis...');

      await startAnalysis(uploadResponse.contract_id);
      setCurrentStage('queued');
      setAnalysisStatus('Analysis queued');

      pollUntilComplete(
        uploadResponse.contract_id,
        (data) => {
          setCurrentStage(statusToStage[data.status] || data.current_stage || 'analyse');
          setAnalysisStatus(data.status_message || 'Analyzing contract...');
        },
        (data) => {
          setCurrentStage('complete');
          setAnalysisStatus('Analysis complete. Opening results...');
          setAnalyzing(false);
          setLoading(false);
          setTimeout(() => {
            navigate(`/results/${uploadResponse.contract_id}`);
          }, 400);
        },
        (err) => {
          setAnalyzing(false);
          setLoading(false);
          setCurrentStage(null);
          setAnalysisStatus('');
          const msg = err.message || 'Analysis failed';
          if (msg.toLowerCase().includes('session') || msg.toLowerCase().includes('log in')) {
            navigate('/login');
            return;
          }
          setError(msg);
        }
      );
    } catch (err) {
      setError(err.message || 'Failed to upload contract');
      setLoading(false);
      setAnalyzing(false);
      setCurrentStage(null);
      setAnalysisStatus('');
    }
  };

  const handleLogout = async () => {
    await signOut();
    navigate('/login');
  };

  const handleExportFromHistory = async (id) => {
    try {
      const { blob, filename } = await exportReport(id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `risk-report.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || 'Failed to export report');
    }
  };

  const handleRerun = async (id) => {
    try {
      setActionLoading(true);
      await rerunAnalysis(id);
      setConfirmRerun(null);
      loadHistory();
    } catch (err) {
      setError(err.message || 'Failed to rerun analysis');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      setActionLoading(true);
      await deleteContract(id);
      setConfirmDelete(null);
      loadHistory();
    } catch (err) {
      setError(err.message || 'Failed to delete contract');
    } finally {
      setActionLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '—';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getHealthScoreColor = (score) => {
    if (score === null || score === undefined) return 'text-gray-400 bg-gray-50';
    if (score < 50) return 'text-red-600 bg-red-50';
    if (score < 75) return 'text-yellow-600 bg-yellow-50';
    return 'text-green-600 bg-green-50';
  };

  const currentStageIndex = progressStages.findIndex((stage) => stage.key === currentStage);
  const showProgress = currentStageIndex >= 0 || analysisStatus;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">Contract Risk Analyzer</h1>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-600 hidden sm:inline">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span className="text-sm font-medium">Logout</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Analyze Section */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6 flex items-center">
            <FileText className="w-5 h-5 mr-2 text-blue-600" />
            Analyze a Contract
          </h2>

          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center">
              <AlertCircle className="w-5 h-5 text-red-500 mr-3" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Contract Type
              </label>
              <select
                value={contractType}
                onChange={(e) => setContractType(e.target.value)}
                disabled={loading}
                className="w-full md:w-1/2 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
              >
                {contractTypes.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Upload PDF
              </label>
              <UploadZone
                onFileSelect={handleFileSelect}
                disabled={loading || analyzing}
              />
            </div>

            <button
              onClick={handleAnalyze}
              disabled={!file || loading || analyzing}
              className="w-full md:w-auto px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 focus:ring-4 focus:ring-blue-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {analyzing ? analysisStatus || 'Analyzing...' : 'Uploading...'}
                </>
              ) : (
                'Analyze Contract'
              )}
            </button>

            {showProgress && (
              <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <p className="text-sm font-medium text-blue-900">
                    {analysisStatus || 'Preparing analysis...'}
                  </p>
                  {contractId && (
                    <span className="hidden sm:inline text-xs text-blue-700 font-mono">
                      {contractId.slice(0, 8)}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-3">
                  {progressStages.map((stage, index) => {
                    const isComplete = currentStage === 'complete' || index < currentStageIndex;
                    const isCurrent = index === currentStageIndex && currentStage !== 'complete';
                    const isPending = !isComplete && !isCurrent;

                    return (
                      <div
                        key={stage.key}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                          isComplete
                            ? 'border-green-200 bg-green-50 text-green-800'
                            : isCurrent
                              ? 'border-blue-300 bg-white text-blue-900'
                              : 'border-gray-200 bg-white text-gray-500'
                        }`}
                      >
                        {isComplete ? (
                          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                        ) : isCurrent ? (
                          <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
                        ) : (
                          <span className="w-4 h-4 flex-shrink-0 rounded-full border border-current text-[10px] flex items-center justify-center">
                            {index + 1}
                          </span>
                        )}
                        <span className="truncate">{stage.label}</span>
                        {isPending && <span className="sr-only">Pending</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* History Section */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Past Analyses</h2>

          {/* Filters */}
          <div className="flex flex-col lg:flex-row gap-3 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                placeholder="Search by filename..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              {statusOptions.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              <option value="">All Types</option>
              {contractTypes.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <select
              value={filterGrade}
              onChange={(e) => setFilterGrade(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              {gradeOptions.map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
            <button
              onClick={applyFilters}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
            >
              <Filter className="w-4 h-4" />
              Filter
            </button>
            {(searchQuery || filterStatus || filterType || filterGrade) && (
              <button
                onClick={clearFilters}
                className="px-3 py-2 bg-gray-100 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-200 transition-colors flex items-center justify-center gap-1"
              >
                <X className="w-4 h-4" />
                Clear
              </button>
            )}
          </div>

          {historyLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
            </div>
          ) : history.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No contracts analyzed yet</p>
              <p className="text-sm text-gray-400 mt-1">Upload your first contract above</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Filename</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Type</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Health Score</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Date</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((contract) => (
                    <tr key={contract.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-4">
                        <div className="flex items-center">
                          <FileText className="w-4 h-4 text-gray-400 mr-2 flex-shrink-0" />
                          <span className="text-sm font-medium text-gray-900 truncate max-w-xs">
                            {contract.filename}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-sm text-gray-700 capitalize">
                          {contract.contract_type}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${statusBadgeClass[contract.status] || 'bg-gray-100 text-gray-700 border-gray-200'}`}>
                          {contract.status}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {contract.health_score !== null && contract.health_score !== undefined ? (
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getHealthScoreColor(contract.health_score)}`}>
                            {contract.health_score}
                          </span>
                        ) : (
                          <span className="text-sm text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center text-sm text-gray-500">
                          <Clock className="w-3 h-3 mr-1 flex-shrink-0" />
                          {formatDate(contract.uploaded_at)}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          {contract.status === 'complete' && (
                            <>
                              <button
                                onClick={() => navigate(`/results/${contract.id}`)}
                                className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                                title="View Results"
                              >
                                <Eye className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleExportFromHistory(contract.id)}
                                className="p-1.5 text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
                                title="Download Report"
                              >
                                <Download className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => setConfirmRerun(contract.id)}
                                className="p-1.5 text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
                                title="Re-run Analysis"
                              >
                                <RefreshCw className="w-4 h-4" />
                              </button>
                            </>
                          )}
                          {contract.status === 'failed' && (
                            <button
                              onClick={() => setConfirmRerun(contract.id)}
                              className="p-1.5 text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
                              title="Re-run Analysis"
                            >
                              <RefreshCw className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => setConfirmDelete(contract.id)}
                            className="p-1.5 text-red-500 hover:bg-red-50 rounded-md transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Contract</h3>
            <p className="text-sm text-gray-600 mb-6">
              This will hide the contract from your history. Running analyses cannot be deleted.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(confirmDelete)}
                disabled={actionLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors disabled:opacity-50"
              >
                {actionLoading ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rerun Confirmation Modal */}
      {confirmRerun && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Re-run Analysis</h3>
            <p className="text-sm text-gray-600 mb-6">
              This will clear old clause analyses and summary fields, then enqueue a fresh analysis using the stored PDF.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmRerun(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleRerun(confirmRerun)}
                disabled={actionLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
              >
                {actionLoading ? 'Queueing...' : 'Re-run'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
