import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, ArrowRight, Sparkles, Package, TrendingUp, Shield, Upload, FileText, CheckCircle, X, Loader } from 'lucide-react';
import toast from 'react-hot-toast';
import { uploadFile } from '../services/api';
import './Welcome.css';

function Welcome() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  // Supported file extensions
  const supportedExtensions = ['.csv', '.json', '.xml', '.txt', '.pdf', '.xlsx', '.xls', '.png', '.jpg', '.jpeg', '.log'];
  
  const getFileIcon = (filename) => {
    const ext = filename.toLowerCase().split('.').pop();
    const icons = {
      csv: '📊', json: '📋', xml: '📄', txt: '📝', 
      pdf: '📕', xlsx: '📗', xls: '📗', 
      png: '🖼️', jpg: '🖼️', jpeg: '🖼️', log: '📜'
    };
    return icons[ext] || '📁';
  };

  const handleUploadData = () => {
    setShowUploadModal(true);
  };

  const handleManualEntry = () => {
    navigate('/data-input');
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFileSelect = (file) => {
    if (file) {
      const ext = '.' + file.name.toLowerCase().split('.').pop();
      if (supportedExtensions.includes(ext)) {
        setUploadedFile(file);
      } else {
        toast.error(`Supported formats: ${supportedExtensions.join(', ')}`);
      }
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleUploadSubmit = async () => {
    if (!uploadedFile) {
      toast.error('Please select a file first');
      return;
    }

    setIsUploading(true);
    try {
      const result = await uploadFile(uploadedFile);
      toast.success(result.message || 'Data uploaded successfully!');
      setTimeout(() => {
        navigate('/dashboard');
      }, 500);
    } catch (error) {
      const status = error.response?.status;
      const detail = error.response?.data?.detail || 'Upload failed. Please try again.';
      
      if (status === 429) {
        // Quota exceeded - show special message
        toast.error('AI quota exceeded! Please wait 1 minute and try again, or use CSV/Excel format.', {
          duration: 6000
        });
      } else {
        toast.error(detail);
      }
      setIsUploading(false);
    }
  };

  const closeModal = () => {
    setShowUploadModal(false);
    setUploadedFile(null);
    setIsDragging(false);
  };

  return (
    <div className="welcome-page">
      <div className="welcome-background">
        <div className="bg-gradient-1"></div>
        <div className="bg-gradient-2"></div>
        <div className="bg-particles"></div>
      </div>

      <div className="welcome-content">
        <div className="welcome-header">
          <div className="welcome-logo">
            <Sparkles className="welcome-logo-icon" />
            <h1>OptiStock</h1>
          </div>
          <p className="welcome-tagline">AI-Powered Procurement Intelligence</p>
        </div>

        <div className="welcome-main">
          <div className="give-data-section">
            <div className="give-data-icon-wrapper">
              <Database className="give-data-icon" />
            </div>
            <h2 className="give-data-title">
              <span className="highlight-text">GIVE THE DATA</span>
            </h2>
            <p className="give-data-subtitle">
              Start by entering your inventory and sales data to unlock powerful AI insights
            </p>
            
            <div className="welcome-buttons">
              <button className="get-started-btn" onClick={handleUploadData}>
                <span>Upload the Data</span>
                <ArrowRight className="btn-icon" />
              </button>
              <button className="skip-btn" onClick={handleManualEntry}>
                <span>Upload Later (Manual Entry)</span>
              </button>
            </div>
          </div>

          <div className="features-preview">
            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <Package />
              </div>
              <h3>Inventory Management</h3>
              <p>Track stock levels and product details</p>
            </div>
            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <TrendingUp />
              </div>
              <h3>Demand Forecasting</h3>
              <p>AI-powered 30-day demand predictions</p>
            </div>
            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <Shield />
              </div>
              <h3>Risk Assessment</h3>
              <p>Supplier risk analysis and alerts</p>
            </div>
          </div>
        </div>

        <div className="welcome-footer">
          <p>Powered by <strong>Google Gemini AI</strong></p>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="upload-modal-overlay" onClick={closeModal}>
          <div className="upload-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={closeModal}>
              <X size={24} />
            </button>
            
            <div className="modal-header">
              <FileText className="modal-icon" />
              <h2>Upload Your Data</h2>
              <p>Supports CSV, JSON, XML, PDF, Excel, Images, Text, and Log files</p>
            </div>

            <div 
              className={`drop-zone ${isDragging ? 'dragging' : ''} ${uploadedFile ? 'has-file' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                accept=".csv,.json,.xml,.txt,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.log"
                onChange={handleFileInputChange}
                style={{ display: 'none' }}
              />
              
              {uploadedFile ? (
                <div className="file-selected">
                  <span className="file-emoji">{getFileIcon(uploadedFile.name)}</span>
                  <span className="file-name">{uploadedFile.name}</span>
                  <span className="file-size">({(uploadedFile.size / 1024).toFixed(1)} KB)</span>
                  <CheckCircle className="file-check success" />
                </div>
              ) : (
                <>
                  <Upload className="drop-icon" />
                  <p className="drop-text">
                    {isDragging ? 'Drop your file here!' : 'Drag & drop any data file here'}
                  </p>
                  <span className="drop-hint">or click to browse</span>
                  <div className="supported-formats">
                    <span>📊 CSV</span>
                    <span>📋 JSON</span>
                    <span>📄 XML</span>
                    <span>📕 PDF</span>
                    <span>📗 Excel</span>
                    <span>🖼️ Images</span>
                  </div>
                </>
              )}
            </div>

            <div className="modal-actions">
              <button 
                className="upload-submit-btn" 
                onClick={handleUploadSubmit}
                disabled={!uploadedFile || isUploading}
              >
                {isUploading ? (
                  <>
                    <Loader className="spinner" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <Upload />
                    <span>Upload & Continue</span>
                  </>
                )}
              </button>
              <button className="upload-cancel-btn" onClick={closeModal}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Welcome;
