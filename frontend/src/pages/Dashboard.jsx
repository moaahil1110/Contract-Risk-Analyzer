import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadContract, startAnalysis, getHistory, pollUntilComplete } from '../lib/api';
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
  Clock
} from 'lucide-react';

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

  const contractTypes = [
    { value: 'nda', label: 'NDA (Non-Disclosure Agreement)' },
    { value: 'employment', label: 'Employment Contract' },
    { value: 'vendor', label: 'Vendor Agreement' },
    { value: 'other', label: 'Other' },
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

  const loadHistory = async () => {
    try {
      setHistoryLoading(true);
      const data = await getHistory();
      setHistory(data.contracts || []);
    } catch (err) {
      console.error('Failed to load history:', err);
      if (err.message?.includes('auth')) {
        navigate('/login');
      }
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleFileSelect = (selectedFile) => {
    setFile(selectedFile);
    setError(null);
  };

  const handleAnalyze = async () => {
    if (!file) {
      setError('Please select a PDF file to analyze');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Upload the file
      setAnalysisStatus('Uploading...');
      const uploadResponse = await uploadContract(file, contractType);
      setContractId(uploadResponse.contract_id);
      setAnalyzing(true);
      setAnalysisStatus('Starting analysis...');

      // Start backend analysis before polling for completed results
      await startAnalysis(uploadResponse.contract_id);
      setAnalysisStatus('Analyzing contract...');

      // Poll for results
      pollUntilComplete(
        uploadResponse.contract_id,
        (data) => {
          setAnalysisStatus(data.status === 'complete' ? 'Complete!' : 'Analyzing contract...');
        },
        (data) => {
          setAnalyzing(false);
          setLoading(false);
          navigate(`/results/${uploadResponse.contract_id}`);
        },
        (err) => {
          setAnalyzing(false);
          setLoading(false);
          setError(err.message || 'Analysis failed');
        }
      );
    } catch (err) {
      setError(err.message || 'Failed to upload contract');
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await signOut();
    navigate('/login');
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getHealthScoreColor = (score) => {
    if (score < 50) return 'text-red-600 bg-red-50';
    if (score < 75) return 'text-yellow-600 bg-yellow-50';
    return 'text-green-600 bg-green-50';
  };

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
            <span className="text-sm text-gray-600">{user?.email}</span>
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
            {/* Contract Type Selector */}
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

            {/* Upload Zone */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Upload PDF
              </label>
              <UploadZone 
                onFileSelect={handleFileSelect} 
                disabled={loading || analyzing} 
              />
            </div>

            {/* Analyze Button */}
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
          </div>
        </div>

        {/* History Section */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Past Analyses</h2>

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
                          <FileText className="w-4 h-4 text-gray-400 mr-2" />
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
                        {contract.health_score ? (
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getHealthScoreColor(contract.health_score)}`}>
                            {contract.health_score}
                          </span>
                        ) : (
                          <span className="text-sm text-gray-400">Processing</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center text-sm text-gray-500">
                          <Clock className="w-3 h-3 mr-1" />
                          {formatDate(contract.uploaded_at)}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <button
                          onClick={() => navigate(`/results/${contract.id}`)}
                          className="flex items-center text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          View
                          <ChevronRight className="w-4 h-4 ml-1" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
