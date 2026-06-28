import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageCircle, X, Mic, MicOff, Send, Loader2, Bot, User, Volume2 } from 'lucide-react';
import toast from 'react-hot-toast';
import './VoiceAssistant.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function VoiceAssistant() {
  const { t, i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const synthRef = useRef(window.speechSynthesis);

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;
      
      // Set language based on current i18n language
      const langMap = { en: 'en-US', ta: 'ta-IN', hi: 'hi-IN' };
      recognitionRef.current.lang = langMap[i18n.language] || 'en-US';

      recognitionRef.current.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsListening(false);
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
        if (event.error === 'not-allowed') {
          toast.error(t('voiceAssistant.micPermissionDenied'));
        }
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
      if (synthRef.current) {
        synthRef.current.cancel();
      }
    };
  }, [i18n.language, t]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Add welcome message when chat opens
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: t('voiceAssistant.welcomeMessage'),
        timestamp: new Date()
      }]);
    }
  }, [isOpen, messages.length, t]);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      toast.error(t('voiceAssistant.speechNotSupported'));
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        console.error('Failed to start speech recognition:', err);
        toast.error(t('voiceAssistant.micError'));
      }
    }
  };

  const speakResponse = (text) => {
    if (!synthRef.current) return;
    
    synthRef.current.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    
    // Set language for speech
    const langMap = { en: 'en-US', ta: 'ta-IN', hi: 'hi-IN' };
    utterance.lang = langMap[i18n.language] || 'en-US';
    utterance.rate = 0.9;
    
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    
    synthRef.current.speak(utterance);
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage.content,
          language: i18n.language
        })
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      
      const assistantMessage = {
        role: 'assistant',
        content: data.response || t('voiceAssistant.noResponse'),
        timestamp: new Date()
      };

      setMessages(prev => [...prev, assistantMessage]);
      
      // Auto-speak response if user used voice input
      if (data.response) {
        speakResponse(data.response);
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage = {
        role: 'assistant',
        content: t('voiceAssistant.errorMessage'),
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const stopSpeaking = () => {
    if (synthRef.current) {
      synthRef.current.cancel();
      setIsSpeaking(false);
    }
  };

  return (
    <>
      {/* Floating Button */}
      <button
        className={`voice-assistant-fab ${isOpen ? 'hidden' : ''}`}
        onClick={() => setIsOpen(true)}
        title={t('voiceAssistant.openChat')}
      >
        <MessageCircle size={24} />
      </button>

      {/* Chat Panel */}
      {isOpen && (
        <div className="voice-assistant-panel">
          <div className="va-header">
            <div className="va-header-title">
              <Bot size={20} />
              <span>{t('voiceAssistant.title')}</span>
            </div>
            <button className="va-close-btn" onClick={() => setIsOpen(false)}>
              <X size={20} />
            </button>
          </div>

          <div className="va-messages">
            {messages.map((msg, idx) => (
              <div key={idx} className={`va-message ${msg.role}`}>
                <div className="va-message-icon">
                  {msg.role === 'assistant' ? <Bot size={16} /> : <User size={16} />}
                </div>
                <div className={`va-message-content ${msg.isError ? 'error' : ''}`}>
                  {msg.content}
                </div>
                {msg.role === 'assistant' && !msg.isError && (
                  <button 
                    className="va-speak-btn"
                    onClick={() => isSpeaking ? stopSpeaking() : speakResponse(msg.content)}
                    title={isSpeaking ? t('voiceAssistant.stopSpeaking') : t('voiceAssistant.speakMessage')}
                  >
                    <Volume2 size={14} className={isSpeaking ? 'speaking' : ''} />
                  </button>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="va-message assistant">
                <div className="va-message-icon">
                  <Bot size={16} />
                </div>
                <div className="va-message-content loading">
                  <Loader2 size={16} className="spin" />
                  <span>{t('voiceAssistant.thinking')}</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="va-input-area">
            <button
              className={`va-mic-btn ${isListening ? 'listening' : ''}`}
              onClick={toggleListening}
              title={isListening ? t('voiceAssistant.stopListening') : t('voiceAssistant.startListening')}
            >
              {isListening ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
            <input
              type="text"
              className="va-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={isListening ? t('voiceAssistant.listening') : t('voiceAssistant.placeholder')}
              disabled={isListening || isLoading}
            />
            <button
              className="va-send-btn"
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              title={t('voiceAssistant.send')}
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
