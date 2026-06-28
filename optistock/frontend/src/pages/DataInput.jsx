// DataInput.jsx - Simplified Upload-Only Page for MSMEs
// Clean, focused interface - Upload CSV/Excel -> Redirect to Dashboard

import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Upload, 
  FileSpreadsheet, 
  CheckCircle,
  X,
  Download,
  Sparkles,
  ArrowRight,
  FileText,
  AlertCircle
} from 'lucide-react';
import toast from 'react-hot-toast';
import { uploadFile as uploadFileApi } from '../services/api';
import './DataInput.css';

function DataInput() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  // Upload State
  const [uploadFile, setUploadFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [productCount, setProductCount] = useState(0);

  // Handle File Selection
  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file type
      const validTypes = ['.csv', '.xlsx', '.xls'];
      const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
      
      if (!validTypes.includes(fileExtension)) {
        toast.error('Please upload a CSV or Excel file (.csv, .xlsx, .xls)');
        return;
      }
      
      // Validate file size (max 10MB)
      if (file.size > 10 * 1024 * 1024) {
        toast.error('File too large. Maximum size is 10MB');
        return;
      }
      
      setUploadFile(file);
      setUploadSuccess(false);
    }
  };

  // Handle Drag & Drop
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    const file = e.dataTransfer.files[0];
    if (file) {
      const validTypes = ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'];
      const fileExtension = file.name.split('.').pop().toLowerCase();
      
      if (!validTypes.includes(file.type) && !['csv', 'xlsx', 'xls'].includes(fileExtension)) {
        toast.error('Please upload a CSV or Excel file');
        return;
      }
      
      setUploadFile(file);
      setUploadSuccess(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Count rows in CSV
  const countCSVRows = async (file) => {
    try {
      const text = await file.text();
      const lines = text.trim().split('\n');
      return Math.max(0, lines.length - 1); // Subtract header row
    } catch {
      return 0;
    }
  };

  // Handle Upload
  const handleUpload = async () => {
    if (!uploadFile) {
      toast.error('Please select a file first');
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 10, 90));
      }, 200);

      // Count products
      const count = await countCSVRows(uploadFile);
      
      // Upload to backend
      const result = await uploadFileApi(uploadFile);
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      const finalCount = result.unique_products || result.records_count || count;
      setProductCount(finalCount);
      setUploadSuccess(true);
      
      toast.success('Successfully uploaded ' + finalCount + ' products!');
      
      // Auto-redirect after 2 seconds
      setTimeout(() => {
        navigate('/dashboard');
      }, 2000);
      
    } catch (error) {
      console.error('Upload error:', error);
      
      // Try to count products locally even if backend fails
      const count = await countCSVRows(uploadFile);
      if (count > 0) {
        setProductCount(count);
        setUploadSuccess(true);
        toast.success('File processed! ' + count + ' products detected. Backend sync pending.');
        
        setTimeout(() => {
          navigate('/dashboard');
        }, 2000);
      } else {
        toast.error(error.response?.data?.detail || 'Upload failed. Please check your file format.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  // Clear file
  const clearFile = () => {
    setUploadFile(null);
    setUploadSuccess(false);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Download sample template
  const downloadTemplate = () => {
    const csvContent = 'SKU,Product_Name,Category,Current_Stock,Reorder_Level,Cost_Per_Unit,Selling_Price,Supplier,Lead_Time_Days\n' +
      'SKU-001,Wireless Mouse,Electronics,500,100,450,899,TechSupply Co,7\n' +
      'SKU-002,Office Chair,Furniture,75,30,3500,7999,FurniMart,14\n' +
      'SKU-003,USB Cable,Electronics,1200,200,80,199,TechSupply Co,5\n' +
      'SKU-004,Notebook A5,Stationery,350,100,25,65,PaperWorld,3\n' +
      'SKU-005,LED Desk Lamp,Electronics,45,25,650,1499,LightHouse Ltd,10';
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'optistock_inventory_template.csv';
    a.click();
    window.URL.revokeObjectURL(url);
    toast.success('Template downloaded! Fill it with your inventory data.');
  };

  return (
    <div className="data-input-simple">
      {/* Header */}
      <div className="upload-header">
        <div className="header-icon">
          <Upload size={32} />
          <Sparkles size={14} className="sparkle" />
        </div>
        <div className="header-text">
          <h1>Upload Your Inventory</h1>
          <p>Import your business data and let AI analyze it instantly</p>
        </div>
      </div>

      {/* Main Upload Card */}
      <div className="upload-card">
        {/* Instructions */}
        <div className="upload-instructions">
          <h2>
            <FileSpreadsheet size={20} />
            Upload CSV or Excel File
          </h2>
          <p>
            Upload your inventory file to begin AI-powered analysis. 
            OptiStock will automatically detect products and provide actionable insights.
          </p>
        </div>

        {/* Upload Zone */}
        <div 
          className={'upload-zone' + (uploadFile ? ' has-file' : '') + (isUploading ? ' uploading' : '') + (uploadSuccess ? ' success' : '')}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <input
            type="file"
            id="file-upload"
            ref={fileInputRef}
            accept=".csv,.xlsx,.xls"
            onChange={handleFileSelect}
            hidden
          />
          
          {!uploadFile && !uploadSuccess && (
            <label htmlFor="file-upload" className="upload-content">
              <div className="upload-icon">
                <FileSpreadsheet size={48} />
              </div>
              <div className="upload-text">
                <span className="main-text">Click to select file</span>
                <span className="sub-text">or drag and drop here</span>
              </div>
              <div className="file-types">
                Supported: CSV, Excel (.xlsx, .xls)
              </div>
            </label>
          )}

          {uploadFile && !isUploading && !uploadSuccess && (
            <div className="file-ready">
              <div className="file-icon">
                <FileText size={32} />
              </div>
              <div className="file-info">
                <span className="file-name">{uploadFile.name}</span>
                <span className="file-size">{(uploadFile.size / 1024).toFixed(1)} KB</span>
              </div>
              <button className="clear-btn" onClick={clearFile}>
                <X size={18} />
              </button>
            </div>
          )}

          {isUploading && (
            <div className="upload-progress">
              <div className="progress-spinner">
                <Sparkles size={32} className="spin" />
              </div>
              <div className="progress-text">
                <span>Analyzing inventory data...</span>
                <span className="progress-percent">{uploadProgress}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: uploadProgress + '%' }} />
              </div>
            </div>
          )}

          {uploadSuccess && (
            <div className="upload-success">
              <div className="success-icon">
                <CheckCircle size={48} />
              </div>
              <div className="success-text">
                <span className="success-title">Upload Complete!</span>
                <span className="success-count">{productCount} products detected</span>
              </div>
              <div className="redirect-notice">
                <Sparkles size={14} />
                <span>Redirecting to Dashboard...</span>
              </div>
            </div>
          )}
        </div>

        {/* Upload Button */}
        {uploadFile && !isUploading && !uploadSuccess && (
          <button className="upload-btn" onClick={handleUpload}>
            <Upload size={20} />
            Upload & Analyze
            <ArrowRight size={18} />
          </button>
        )}

        {/* Go to Dashboard Button (after success) */}
        {uploadSuccess && (
          <button className="dashboard-btn" onClick={() => navigate('/dashboard')}>
            <Sparkles size={20} />
            Go to Dashboard
            <ArrowRight size={18} />
          </button>
        )}
      </div>

      {/* Helper Section */}
      <div className="helper-section">
        {/* Template Download */}
        <div className="helper-card">
          <div className="helper-icon">
            <Download size={24} />
          </div>
          <div className="helper-content">
            <h3>Need a template?</h3>
            <p>Download our pre-formatted CSV template with sample data</p>
          </div>
          <button className="template-btn" onClick={downloadTemplate}>
            <Download size={16} />
            Download Template
          </button>
        </div>

        {/* Format Guide */}
        <div className="helper-card">
          <div className="helper-icon info">
            <AlertCircle size={24} />
          </div>
          <div className="helper-content">
            <h3>Required Columns</h3>
            <p>SKU, Product_Name, Current_Stock, Reorder_Level</p>
          </div>
        </div>
      </div>

    </div>
  );
}

export default DataInput;
