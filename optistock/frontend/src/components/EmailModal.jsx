import React, { useState, useEffect } from 'react';
import { X, Send, Mail, Loader2, Sparkles } from 'lucide-react';
import { sendEmail, analyzeSku } from '../services/api';
import toast from 'react-hot-toast';
import './EmailModal.css';

function EmailModal({ isOpen, onClose, emailData, sku }) {
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);

  // When modal opens with a SKU, fetch AI-generated draft
  useEffect(() => {
    if (!isOpen || !sku) return;

    // Reset fields
    setRecipient('');
    setSubject('');
    setBody('');

    let cancelled = false;
    setGenerating(true);

    analyzeSku(sku)
      .then((result) => {
        if (cancelled) return;
        if (result?.email_draft?.subject && result?.email_draft?.body) {
          setSubject(result.email_draft.subject);
          setBody(result.email_draft.body);
        } else {
          // AI returned no draft (e.g. decision was "Hold") — use fallback
          applyFallback();
        }
      })
      .catch(() => {
        if (cancelled) return;
        applyFallback();
      })
      .finally(() => {
        if (!cancelled) setGenerating(false);
      });

    return () => { cancelled = true; };
  }, [isOpen, sku]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyFallback = () => {
    if (emailData) {
      setSubject(emailData.subject || '');
      setBody(emailData.body || '');
    }
  };

  if (!isOpen) return null;

  const handleSend = async () => {
    if (!recipient) {
      toast.error('Please enter a recipient email');
      return;
    }

    setSending(true);
    try {
      await sendEmail({
        to_email: recipient,
        subject: subject,
        body: body,
        sku: sku
      });
      toast.success('Email sent successfully!');
      onClose();
    } catch (error) {
      toast.error(error.message || 'Failed to send email');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal email-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-row">
            <Mail size={20} />
            <h2>Send Procurement Email</h2>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {generating ? (
            <div className="email-generating">
              <div className="generating-spinner">
                <Sparkles size={28} className="spin" />
              </div>
              <div className="generating-text">
                <span className="generating-title">Generating AI Email Draft...</span>
                <span className="generating-sub">Analyzing inventory data for {sku} to compose a tailored procurement email</span>
              </div>
            </div>
          ) : (
            <>
              <div className="form-group">
                <label>Recipient Email *</label>
                <input
                  type="email"
                  className="input"
                  placeholder="supplier@example.com"
                  value={recipient}
                  onChange={e => setRecipient(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Subject</label>
                <input
                  type="text"
                  className="input"
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Message</label>
                <textarea
                  className="input"
                  rows={12}
                  value={body}
                  onChange={e => setBody(e.target.value)}
                />
              </div>

              <div className="email-info">
                <p><Sparkles size={13} /> AI-generated based on real-time inventory & forecast data. Edit freely before sending.</p>
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={sending || generating || !recipient}
          >
            {sending ? (
              <>
                <Loader2 size={16} className="spin" />
                Sending...
              </>
            ) : (
              <>
                <Send size={16} />
                Send Email
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default EmailModal;
