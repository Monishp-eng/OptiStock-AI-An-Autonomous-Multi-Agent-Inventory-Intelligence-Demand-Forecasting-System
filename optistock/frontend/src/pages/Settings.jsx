import React, { useState, useEffect } from 'react';
import { Mail, CheckCircle, XCircle, Send, Loader2, Globe } from 'lucide-react';
import { getEmailConfig, sendTestEmail } from '../services/api';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import './Settings.css';

function Settings() {
  const [emailConfig, setEmailConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testingSending, setTestingSending] = useState(false);
  const { t, i18n } = useTranslation();

  const handleLanguageChange = (lang) => {
    i18n.changeLanguage(lang);
    localStorage.setItem('optistock_lang', lang);
  };

  useEffect(() => {
    fetchEmailConfig();
  }, []);

  const fetchEmailConfig = async () => {
    try {
      const config = await getEmailConfig();
      setEmailConfig(config);
    } catch (error) {
      toast.error('Failed to load email configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleTestEmail = async () => {
    setTestingSending(true);
    try {
      await sendTestEmail();
      toast.success('Test email sent successfully!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send test email');
    } finally {
      setTestingSending(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <Loader2 size={40} className="spin" />
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>{t('settings.title')}</h1>
        <p>{t('settings.subtitle')}</p>
      </div>

      {/* Language Switcher */}
      <div className="settings-section">
        <div className="section-header">
          <Globe size={24} />
          <div>
            <h2>{t('settings.language')}</h2>
            <p>{t('settings.languageSubtitle')}</p>
          </div>
        </div>
        <div className="settings-card">
          <div className="lang-buttons">
            <button
              className={`btn ${i18n.language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => handleLanguageChange('en')}
            >
              {t('settings.english')}
            </button>
            <button
              className={`btn ${i18n.language === 'ta' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => handleLanguageChange('ta')}
            >
              {t('settings.tamil')}
            </button>
            <button
              className={`btn ${i18n.language === 'hi' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => handleLanguageChange('hi')}
            >
              {t('settings.hindi')}
            </button>
          </div>
        </div>
      </div>

      {/* Email Configuration */}
      <div className="settings-section">
        <div className="section-header">
          <Mail size={24} />
          <div>
            <h2>Email Configuration</h2>
            <p>SMTP settings for sending procurement emails</p>
          </div>
        </div>

        <div className="settings-card">
          <div className="config-status">
            {emailConfig?.configured ? (
              <div className="status-row success">
                <CheckCircle size={20} />
                <span>Email is configured and ready</span>
              </div>
            ) : (
              <div className="status-row warning">
                <XCircle size={20} />
                <span>Email not configured</span>
              </div>
            )}
          </div>

          <div className="config-details">
            <div className="config-item">
              <span className="config-label">SMTP Host</span>
              <span className="config-value">{emailConfig?.smtp_host || 'Not set'}</span>
            </div>
            <div className="config-item">
              <span className="config-label">SMTP Port</span>
              <span className="config-value">{emailConfig?.smtp_port || 'Not set'}</span>
            </div>
            <div className="config-item">
              <span className="config-label">Email Address</span>
              <span className="config-value">
                {emailConfig?.email_address || 'Not configured'}
              </span>
            </div>
          </div>

          {emailConfig?.configured && (
            <div className="config-actions">
              <button 
                className="btn btn-primary"
                onClick={handleTestEmail}
                disabled={testingSending}
              >
                {testingSending ? (
                  <>
                    <Loader2 size={16} className="spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send size={16} />
                    Send Test Email
                  </>
                )}
              </button>
            </div>
          )}

          {!emailConfig?.configured && (
            <div className="config-help">
              <h4>How to Configure Email</h4>
              <p>Set these environment variables on your server:</p>
              <div className="code-block">
                <code>SMTP_EMAIL=your-email@gmail.com</code>
                <code>SMTP_PASSWORD=your-app-password</code>
                <code>SMTP_HOST=smtp.gmail.com</code>
                <code>SMTP_PORT=587</code>
              </div>
              <p className="help-note">
                For Gmail, you need to create an App Password at{' '}
                <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">
                  Google Account Settings
                </a>
              </p>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

export default Settings;
