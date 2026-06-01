import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File, X } from 'lucide-react';

const UploadZone = ({ onFileSelect, disabled = false }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [error, setError] = useState(null);

  const onDrop = useCallback(
    (acceptedFiles, rejectedFiles) => {
      setError(null);

      if (rejectedFiles.length > 0) {
        const rejection = rejectedFiles[0];
        const errorMessage = rejection.errors?.[0]?.message || 'Invalid file';
        setError(errorMessage);
        return;
      }

      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
    },
    multiple: false,
    disabled,
  });

  const clearFile = () => {
    setSelectedFile(null);
    setError(null);
    onFileSelect(null);
  };

  if (selectedFile) {
    return (
      <div className="border-2 border-solid border-green-500 rounded-lg p-6 bg-green-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <File className="w-8 h-8 text-green-600" />
            <div>
              <p className="font-medium text-gray-900">{selectedFile.name}</p>
              <p className="text-sm text-gray-500">
                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>
          {!disabled && (
            <button
              onClick={clearFile}
              className="p-1 hover:bg-green-100 rounded-full transition-colors"
            >
              <X className="w-5 h-5 text-gray-500" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          isDragActive
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <input {...getInputProps()} />
        <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
        <p className="text-lg font-medium text-gray-700 mb-2">
          {isDragActive ? 'Drop the PDF here' : 'Drag & drop your contract PDF'}
        </p>
        <p className="text-sm text-gray-500 mb-4">or click to browse</p>
        <p className="text-xs text-gray-400">Only PDF files are accepted</p>
      </div>

      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}
    </div>
  );
};

export default UploadZone;
