/**
 * OptiStock — Central API Service (fetch-based)
 * All HTTP calls to the FastAPI backend go through this module.
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Internal helper — every call funnels through here for consistent errors
// ---------------------------------------------------------------------------

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {};

  // Only set Content-Type for JSON bodies (not for FormData — browser adds
  // its own multipart boundary header automatically)
  if (!(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  // Inject JWT token on every call — read from localStorage HERE (not at
  // module scope) so the value is always fresh after login/logout.
  const token = localStorage.getItem('optistock_token');
  if (token) {
    defaultHeaders['Authorization'] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      // Try to extract a FastAPI error detail
      let errorDetail;
      try {
        const errJson = await response.json();
        errorDetail = errJson.detail || errJson.message || JSON.stringify(errJson);
      } catch {
        errorDetail = response.statusText;
      }
      throw new Error(`API ${response.status}: ${errorDetail}`);
    }

    return response.json();
  } catch (error) {
    if (error.message.startsWith('API ')) {
      throw error; // Re-throw structured API errors as-is
    }
    // Network / CORS / timeout errors
    console.error(`[OptiStock API] ${options.method || 'GET'} ${endpoint} failed:`, error);
    throw new Error(
      'Network error — could not reach the server. Is the backend running?'
    );
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const checkHealth = () => request('/health');

export const checkEnhancedHealth = () => request('/api/v2/health');

// ---------------------------------------------------------------------------
// Inventory
// ---------------------------------------------------------------------------

/** Fetch all inventory items (includes risk_level & days_of_stock). */
export const getInventory = () => request('/api/inventory');

export const getInventoryBySku = (sku) =>
  request(`/api/inventory/${encodeURIComponent(sku)}`);

export const createInventoryItem = (item) =>
  request('/api/inventory', {
    method: 'POST',
    body: JSON.stringify(item),
  });

// ---------------------------------------------------------------------------
// Forecast
// ---------------------------------------------------------------------------

/** Get 30-day demand forecast for a single SKU. */
export const getForecast = (sku) =>
  request(`/api/forecast/${encodeURIComponent(sku)}`);

// ---------------------------------------------------------------------------
// Agent Analysis (v1)
// ---------------------------------------------------------------------------

export const analyzeSku = (sku) =>
  request(`/api/agent/analyze/${encodeURIComponent(sku)}`, { method: 'POST' });

export const analyzeAllSkus = () =>
  request('/api/agent/analyze-all', { method: 'POST' });

export const analyzeAndSendEmail = (sku, recipientEmail) => {
  const params = recipientEmail
    ? `?recipient_email=${encodeURIComponent(recipientEmail)}`
    : '';
  return request(
    `/api/agent/analyze-and-send/${encodeURIComponent(sku)}${params}`,
    { method: 'POST' }
  );
};

// ---------------------------------------------------------------------------
// Enhanced v2 — Gemini-powered analysis
// ---------------------------------------------------------------------------

/**
 * AI-powered SKU analysis via Gemini.
 * Returns { explanation, reorderUrgency, recommendation } in plain language.
 */
export const enhancedAnalyzeSku = (sku) =>
  request(`/api/v2/analyze/${encodeURIComponent(sku)}`, { method: 'POST' });

export const enhancedAnalyzeAll = () =>
  request('/api/v2/analyze-all', { method: 'POST' });

export const naturalLanguageQuery = (query, includeAnalytics = true) =>
  request('/api/v2/query', {
    method: 'POST',
    body: JSON.stringify({ query, include_analytics: includeAnalytics }),
  });

export const generateReport = (reportType, options = {}) =>
  request('/api/v2/report', {
    method: 'POST',
    body: JSON.stringify({
      report_type: reportType,
      period: options.period || 'weekly',
      sku: options.sku,
      email_type: options.emailType,
      email_context: options.emailContext,
    }),
  });

export const getExecutiveSummary = (period = 'weekly') =>
  generateReport('executive_summary', { period });

export const getProcurementRecommendation = (sku) =>
  generateReport('procurement', { sku });

export const generateSupplierEmail = (emailType, context) =>
  generateReport('email', { emailType, emailContext: context });

export const scoreSupplier = (supplierData) =>
  request('/api/v2/supplier/score', {
    method: 'POST',
    body: JSON.stringify(supplierData),
  });

export const getSampleQueries = () => request('/api/v2/sample-queries');

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

/**
 * Upload a CSV or Excel inventory file.
 * Accepts a File object; sends it as multipart/form-data.
 */
export const uploadInventory = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return request('/api/upload', {
    method: 'POST',
    body: formData,
    // No explicit Content-Type — browser sets multipart boundary automatically
  });
};

// Legacy aliases so existing pages keep working
export const uploadFile = uploadInventory;
export const uploadCSV = uploadInventory;

// ---------------------------------------------------------------------------
// Data management
// ---------------------------------------------------------------------------

export const getDataStatus = () => request('/api/data-status');

export const clearData = () => request('/api/data-clear', { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Email
// ---------------------------------------------------------------------------

export const getEmailConfig = () => request('/api/email/config');

export const sendEmail = (emailData) =>
  request('/api/email/send', {
    method: 'POST',
    body: JSON.stringify(emailData),
  });

export const sendTestEmail = () =>
  request('/api/email/test', { method: 'POST' });

// ---------------------------------------------------------------------------
// Convenience helpers
// ---------------------------------------------------------------------------

export const isEnhancedApiAvailable = async () => {
  try {
    const health = await checkEnhancedHealth();
    return health && health.status === 'healthy';
  } catch {
    return false;
  }
};

export const getEnhancedInventory = async () => {
  try {
    const [inventory, enhancedAvailable] = await Promise.all([
      getInventory(),
      isEnhancedApiAvailable(),
    ]);
    if (!enhancedAvailable || !inventory.items) {
      return inventory;
    }
    return { ...inventory, enhanced_available: true };
  } catch (error) {
    console.error('Error fetching enhanced inventory:', error);
    return getInventory();
  }
};

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const getAuthStatus = () => request('/api/auth/status');

export const registerUser = (username, password) =>
  request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });

export const loginUser = (username, password) =>
  request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });

export const getMe = () => request('/api/auth/me');

// ---------------------------------------------------------------------------
// Sales
// ---------------------------------------------------------------------------

export const recordSale = (sku, quantity, saleDate) =>
  request('/api/sales', {
    method: 'POST',
    body: JSON.stringify({ sku, quantity, sale_date: saleDate }),
  });

export const getSales = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v != null && v !== '')
  ).toString();
  return request(`/api/sales${qs ? '?' + qs : ''}`);
};

export const getSalesSummary = () => request('/api/sales/summary');

// ---------------------------------------------------------------------------
// Suppliers
// ---------------------------------------------------------------------------

export const getSuppliers = () => request('/api/suppliers');

export const createSupplier = (supplier) =>
  request('/api/suppliers', {
    method: 'POST',
    body: JSON.stringify(supplier),
  });

export const updateSupplier = (id, supplier) =>
  request(`/api/suppliers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(supplier),
  });

export const deleteSupplier = (id) =>
  request(`/api/suppliers/${id}`, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Purchase Orders
// ---------------------------------------------------------------------------

export const getOrders = (status) => {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return request(`/api/orders${qs}`);
};

export const createOrder = (order) =>
  request('/api/orders', {
    method: 'POST',
    body: JSON.stringify(order),
  });

export const updateOrderStatus = (id, status) =>
  request(`/api/orders/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });

export const deleteOrder = (id) =>
  request(`/api/orders/${id}`, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Profit
// ---------------------------------------------------------------------------

export const getProfitSummary = () => request('/api/profit-summary');

export const updateSellingPrice = (sku, sellingPrice) =>
  request(`/api/inventory/${encodeURIComponent(sku)}/selling-price`, {
    method: 'PUT',
    body: JSON.stringify({ selling_price: sellingPrice }),
  });

// ---------------------------------------------------------------------------
// Export (download helpers — return raw Response for blob handling)
// ---------------------------------------------------------------------------

export const downloadExcel = () => {
  const token = localStorage.getItem('optistock_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  return fetch(`${API_BASE_URL}/api/export/excel`, { headers });
};

export const downloadPdf = () => {
  const token = localStorage.getItem('optistock_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  return fetch(`${API_BASE_URL}/api/export/pdf`, { headers });
};

// ---------------------------------------------------------------------------
// AI Agents
// ---------------------------------------------------------------------------

/** Get the full agent dashboard (all agents, events, cycles). */
export const getAgentDashboard = () => request('/api/agents/dashboard');

/** Get status of all agents. */
export const getAgentsStatus = () => request('/api/agents/status');

/** Get detailed status and history for a specific agent. */
export const getAgentDetail = (agentName) => request(`/api/agents/${agentName}`);

/** Enable or disable a specific agent. */
export const toggleAgent = (agentName, enabled) =>
  request(`/api/agents/${agentName}/toggle`, {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });

/** Trigger a specific agent to run. */
export const runAgent = (agentName, context = {}) =>
  request(`/api/agents/${agentName}/run`, {
    method: 'POST',
    body: JSON.stringify({ context }),
  });

/** Get run history for a specific agent. */
export const getAgentHistory = (agentName) =>
  request(`/api/agents/${agentName}/history`);

/** Run an agent cycle (monitoring, procurement, full, report). */
export const runAgentCycle = (cycleType, reportType = 'daily_summary') =>
  request('/api/agents/cycles/run', {
    method: 'POST',
    body: JSON.stringify({ cycle_type: cycleType, report_type: reportType }),
  });

/** Get cycle history. */
export const getCycleHistory = () => request('/api/agents/cycles/history');

/** Get recent inter-agent events. */
export const getAgentEvents = (limit = 50, eventType = null) => {
  let url = `/api/agents/events?limit=${limit}`;
  if (eventType) url += `&event_type=${eventType}`;
  return request(url);
};

/** Get agent notifications. */
export const getAgentNotifications = (limit = 20) =>
  request(`/api/agents/notifications?limit=${limit}`);
