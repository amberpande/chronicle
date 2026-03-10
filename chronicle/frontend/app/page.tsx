'use client';

import { useState, useEffect } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const USER_ID = 'demo-user'; // In production, get from Clerk auth

interface Memory {
  content: string;
  score: number;
  decay_weight: number;
  domain: string;
  memory_type: string;
  memory_id: string;
}

interface Stats {
  total: number;
  by_type: Record<string, number>;
  by_domain: Record<string, number>;
  free_limit: number;
}

export default function Chronicle() {
  const [activeTab, setActiveTab] = useState<'add' | 'query'>('add');
  const [noteContent, setNoteContent] = useState('');
  const [queryText, setQueryText] = useState('');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const res = await fetch(`${API_URL}/stats/${USER_ID}`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const handleIngestText = async () => {
    if (!noteContent.trim()) return;

    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(`${API_URL}/ingest/text/${USER_ID}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: noteContent, source: 'paste' }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();

      if (data.written) {
        setMessage(`Note stored! Surprise: ${data.surprise_score}, Novelty: ${data.novelty_score}`);
        setNoteContent('');
        loadStats();
      } else {
        setMessage(data.message);
      }
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : 'Failed to store note'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async () => {
    if (!file) return;

    setLoading(true);
    setMessage('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_URL}/ingest/file/${USER_ID}`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      setMessage(data.message);
      setFile(null);
      loadStats();
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : 'Failed to upload file'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleQuery = async () => {
    if (!queryText.trim()) return;

    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(`${API_URL}/query/${USER_ID}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: queryText, top_k: 5 }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      setMemories(data.results);
      setMessage(data.count > 0 ? `Found ${data.count} relevant memories` : 'No memories found');
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : 'Failed to query memories'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMemory = async (memoryId: string) => {
    try {
      const res = await fetch(`${API_URL}/memory/${USER_ID}/${memoryId}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }
      setMemories(memories.filter(m => m.memory_id !== memoryId));
      loadStats();
      setMessage('Memory deleted');
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : 'Failed to delete memory'}`);
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-950/50 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Chronicle</h1>
              <p className="text-slate-600 dark:text-slate-400 mt-1">Your second brain, but with actual memory</p>
            </div>

            {stats && (
              <div className="flex gap-4 text-sm">
                <div className="text-center px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg">
                  <div className="text-2xl font-bold text-slate-900 dark:text-white">{stats.total}</div>
                  <div className="text-slate-600 dark:text-slate-400">Memories</div>
                </div>
                <div className="text-center px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg">
                  <div className="text-2xl font-bold text-slate-900 dark:text-white">{stats.free_limit - stats.total}</div>
                  <div className="text-slate-600 dark:text-slate-400">Remaining</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('add')}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'add'
                ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-lg'
                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700'
            }`}
          >
            Add Notes
          </button>
          <button
            onClick={() => setActiveTab('query')}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'query'
                ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-lg'
                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700'
            }`}
          >
            Query Memories
          </button>
        </div>

        {/* Message Bar */}
        {message && (
          <div className="mb-6 p-4 bg-slate-100 dark:bg-slate-800 rounded-lg text-slate-900 dark:text-white">
            {message}
          </div>
        )}

        {/* Add Notes Tab */}
        {activeTab === 'add' && (
          <div className="space-y-6">
            {/* Text Input */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">Add Note</h2>
              <textarea
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                placeholder="Paste or type your notes here... Chronicle will automatically extract entities, relationships, and key insights."
                className="w-full h-64 p-4 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-slate-900 dark:focus:ring-white focus:border-transparent resize-none"
              />
              <button
                onClick={handleIngestText}
                disabled={loading || !noteContent.trim()}
                className="mt-4 px-6 py-3 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-lg font-medium hover:bg-slate-800 dark:hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {loading ? 'Processing...' : 'Store Note'}
              </button>
            </div>

            {/* File Upload */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">Upload File</h2>
              <div className="border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg p-8 text-center">
                <input
                  type="file"
                  accept=".txt,.md,.markdown,.pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="file-upload"
                />
                <label
                  htmlFor="file-upload"
                  className="cursor-pointer text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                >
                  {file ? (
                    <div className="space-y-2">
                      <div className="text-lg font-medium text-slate-900 dark:text-white">{file.name}</div>
                      <div className="text-sm text-slate-500">{(file.size / 1024).toFixed(1)} KB</div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-4xl">[ file ]</div>
                      <div className="text-lg font-medium">Click to upload</div>
                      <div className="text-sm">Supports .txt, .md, .pdf</div>
                    </div>
                  )}
                </label>
              </div>
              {file && (
                <button
                  onClick={handleFileUpload}
                  disabled={loading}
                  className="mt-4 px-6 py-3 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-lg font-medium hover:bg-slate-800 dark:hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {loading ? 'Uploading...' : 'Upload File'}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Query Tab */}
        {activeTab === 'query' && (
          <div className="space-y-6">
            {/* Query Input */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">Search Your Memories</h2>
              <input
                type="text"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                placeholder="What are you working on? Chronicle will surface relevant notes..."
                className="w-full p-4 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-slate-900 dark:focus:ring-white focus:border-transparent"
              />
              <button
                onClick={handleQuery}
                disabled={loading || !queryText.trim()}
                className="mt-4 px-6 py-3 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-lg font-medium hover:bg-slate-800 dark:hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {loading ? 'Searching...' : 'Search'}
              </button>
            </div>

            {/* Results */}
            {memories.length > 0 && (
              <div className="space-y-4">
                {memories.map((memory) => (
                  <div
                    key={memory.memory_id}
                    className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6 hover:shadow-xl transition-shadow"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-3">
                          <span className="px-3 py-1 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-medium rounded-full">
                            {memory.memory_type}
                          </span>
                          <span className="px-3 py-1 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-medium rounded-full">
                            {memory.domain}
                          </span>
                          <span className="text-sm text-slate-500 dark:text-slate-400">
                            Score: {memory.score} • Decay: {memory.decay_weight}
                          </span>
                        </div>
                        <p className="text-slate-900 dark:text-white whitespace-pre-wrap leading-relaxed">
                          {memory.content}
                        </p>
                      </div>
                      <button
                        onClick={() => handleDeleteMemory(memory.memory_id)}
                        className="text-slate-400 hover:text-red-500 transition-colors"
                        title="Delete memory"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {memories.length === 0 && queryText && !loading && (
              <div className="text-center py-12 text-slate-500 dark:text-slate-400">
                No memories found. Try adding some notes first!
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
