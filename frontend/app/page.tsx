"use client";

import { useState } from "react";

// Types
interface Persona {
  username: string;
  name: string;
  background: string;
  style: string;
  expertise: string;
  quirks: string[];
  posting_patterns: string;
}

interface Post {
  post_id: string;
  subreddit: string;
  author: string;
  title: string;
  body: string;
  post_type: string;
  target_query: string;
  scheduled_time: string;
}

interface Comment {
  comment_id: string;
  post_id: string;
  author: string;
  body: string;
  parent_comment_id: string | null;
  is_reply: boolean;
}

interface Calendar {
  week_number: number;
  generated_at: string;
  posts: Post[];
  comments: Comment[];
  quality_score: number;
  total_posts: number;
  total_comments: number;
}

const API_URL = "http://localhost:8000";

export default function RedditMastermind() {
  const [companyInfo, setCompanyInfo] = useState(
    "Slideforge is an AI-powered presentation tool that helps users create professional slide decks from outlines. It offers smart layouts, visual suggestions, and exports to PowerPoint, Google Slides, and PDF. Target users include startup founders, consultants, sales teams, and educators."
  );
  const [subreddits, setSubreddits] = useState("r/startups, r/productivity, r/entrepreneur");
  const [queries, setQueries] = useState("presentation tools, pitch deck help, slide design");
  const [postsPerWeek, setPostsPerWeek] = useState(3);
  const [weekNumber, setWeekNumber] = useState(1);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [calendar, setCalendar] = useState<Calendar | null>(null);

  const loadExample = async () => {
    try {
      const response = await fetch(`${API_URL}/api/example`);
      const data = await response.json();

      setCompanyInfo(data.company_info);
      setSubreddits(data.subreddits.join(", "));
      setQueries(data.target_queries.join(", "));
      setPostsPerWeek(data.posts_per_week);
      setWeekNumber(data.week_number);
      setError("");
    } catch (err) {
      setError("Failed to load example: " + (err as Error).message);
    }
  };

  const generateCalendar = async () => {
    setError("");

    // Validate
    if (!companyInfo || companyInfo.length < 50) {
      setError("Company info must be at least 50 characters");
      return;
    }

    const subredditList = subreddits.split(",").map(s => s.trim());
    if (subredditList.some(s => !s.startsWith("r/"))) {
      setError("All subreddits must start with r/");
      return;
    }

    setLoading(true);

    try {
      // Get example personas
      const exampleResponse = await fetch(`${API_URL}/api/example`);
      const exampleData = await exampleResponse.json();

      // Build request
      const request = {
        company_info: companyInfo,
        personas: exampleData.personas,
        subreddits: subredditList,
        target_queries: queries.split(",").map(q => q.trim()),
        posts_per_week: postsPerWeek,
        week_number: weekNumber
      };

      // Generate
      const response = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(request)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      const result = await response.json();
      setCalendar(result);

    } catch (err) {
      setError("Failed to generate calendar: " + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const generateNextWeek = async () => {
    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/generate-next-week`, {
        method: "POST"
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      const result = await response.json();
      setCalendar(result);
      setWeekNumber(result.week_number);

    } catch (err) {
      setError("Failed to generate next week: " + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const downloadCalendar = () => {
    if (!calendar) return;

    const dataStr = JSON.stringify(calendar, null, 2);
    const dataUri = "data:application/json;charset=utf-8," + encodeURIComponent(dataStr);

    const exportFileDefaultName = `reddit-calendar-week-${calendar.week_number}.json`;

    const linkElement = document.createElement("a");
    linkElement.setAttribute("href", dataUri);
    linkElement.setAttribute("download", exportFileDefaultName);
    linkElement.click();
  };

  const getCommentsForPost = (postId: string) => {
    return calendar?.comments.filter(c => c.post_id === postId) || [];
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 to-purple-800 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-lg p-6 md:p-8 mb-6">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-800 mb-2">
            🚀 Reddit Mastermind
          </h1>
          <p className="text-gray-600">
            Generate authentic Reddit content calendars with AI
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border-2 border-red-200 text-red-700 rounded-lg p-4 mb-6">
            {error}
          </div>
        )}

        {/* Configuration Form */}
        <div className="bg-white rounded-lg shadow-lg p-6 md:p-8 mb-6">
          <h2 className="text-xl font-bold text-gray-800 mb-6">📝 Configuration</h2>

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Company Info *
              </label>
              <textarea
                value={companyInfo}
                onChange={(e) => setCompanyInfo(e.target.value)}
                className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                rows={4}
                placeholder="Describe your company, product, and target audience..."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Subreddits (comma-separated) *
              </label>
              <input
                type="text"
                value={subreddits}
                onChange={(e) => setSubreddits(e.target.value)}
                className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                placeholder="r/startups, r/productivity"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Target Queries (comma-separated) *
              </label>
              <input
                type="text"
                value={queries}
                onChange={(e) => setQueries(e.target.value)}
                className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                placeholder="presentation tools, pitch deck help"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Posts Per Week *
                </label>
                <input
                  type="number"
                  value={postsPerWeek}
                  onChange={(e) => setPostsPerWeek(parseInt(e.target.value))}
                  min={1}
                  max={15}
                  className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Week Number
                </label>
                <input
                  type="number"
                  value={weekNumber}
                  onChange={(e) => setWeekNumber(parseInt(e.target.value))}
                  min={1}
                  max={52}
                  className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
            </div>

            <div className="bg-blue-50 border-2 border-blue-200 text-blue-700 rounded-lg p-4">
              💡 <strong>Note:</strong> Personas are pre-configured for this demo. In production, you'd configure them here too.
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={generateCalendar}
                disabled={loading}
                className="bg-gradient-to-r from-purple-600 to-purple-700 text-white px-6 py-3 rounded-lg font-semibold hover:shadow-lg transform hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
              >
                {loading ? "⏳ Generating..." : "🎯 Generate Calendar"}
              </button>

              <button
                onClick={loadExample}
                disabled={loading}
                className="bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold hover:shadow-lg transform hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                📋 Load Example
              </button>
            </div>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-white rounded-lg shadow-lg p-8 md:p-12 text-center mb-6">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-gray-200 border-t-purple-600 mb-4"></div>
            <p className="text-gray-800 font-semibold mb-2">Generating your content calendar...</p>
            <p className="text-gray-600 text-sm">This may take 2-5 minutes</p>
          </div>
        )}

        {/* Results */}
        {calendar && !loading && (
          <>
            {/* Overview */}
            <div className="bg-white rounded-lg shadow-lg p-6 md:p-8 mb-6">
              <h2 className="text-xl font-bold text-gray-800 mb-6">📊 Calendar Overview</h2>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase mb-1">Week</div>
                  <div className="text-2xl font-bold text-gray-800">{calendar.week_number}</div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase mb-1">Posts</div>
                  <div className="text-2xl font-bold text-gray-800">{calendar.total_posts}</div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase mb-1">Comments</div>
                  <div className="text-2xl font-bold text-gray-800">{calendar.total_comments}</div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase mb-1">Quality</div>
                  <div className="text-2xl font-bold text-gray-800">{calendar.quality_score.toFixed(1)}/10</div>
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={generateNextWeek}
                  disabled={loading}
                  className="bg-gradient-to-r from-purple-600 to-purple-700 text-white px-6 py-3 rounded-lg font-semibold hover:shadow-lg transform hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ▶️ Generate Next Week
                </button>

                <button
                  onClick={downloadCalendar}
                  className="bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold hover:shadow-lg transform hover:-translate-y-0.5 transition-all"
                >
                  💾 Download JSON
                </button>
              </div>
            </div>

            {/* Posts */}
            <div className="bg-white rounded-lg shadow-lg p-6 md:p-8 mb-6">
              <h2 className="text-xl font-bold text-gray-800 mb-6">📝 Posts</h2>

              <div className="space-y-4">
                {calendar.posts.map((post) => {
                  const postComments = getCommentsForPost(post.post_id);

                  return (
                    <div
                      key={post.post_id}
                      className="bg-gray-50 rounded-lg p-5 border-l-4 border-purple-500"
                    >
                      <div className="flex flex-wrap gap-2 text-sm text-gray-600 mb-3">
                        <span className="bg-white px-3 py-1 rounded-full font-medium">
                          {post.subreddit}
                        </span>
                        <span className="bg-white px-3 py-1 rounded-full">
                          u/{post.author}
                        </span>
                        <span className="bg-white px-3 py-1 rounded-full">
                          {post.post_type}
                        </span>
                        <span className="bg-white px-3 py-1 rounded-full">
                          📅 {post.scheduled_time}
                        </span>
                      </div>

                      <h3 className="text-lg font-semibold text-gray-800 mb-3">
                        {post.title}
                      </h3>

                      <p className="text-gray-700 leading-relaxed mb-3 whitespace-pre-wrap">
                        {post.body.substring(0, 300)}
                        {post.body.length > 300 && "..."}
                      </p>

                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-purple-600 font-medium">
                          💬 {postComments.length} comments
                        </span>
                        <span className="text-gray-400">•</span>
                        <span className="text-gray-600">
                          🎯 {post.target_query}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Comments */}
            <div className="bg-white rounded-lg shadow-lg p-6 md:p-8">
              <h2 className="text-xl font-bold text-gray-800 mb-6">💬 Comments</h2>

              <div className="space-y-4">
                {calendar.comments.map((comment) => {
                  const post = calendar.posts.find(p => p.post_id === comment.post_id);
                  const authorInitial = comment.author ? comment.author.charAt(0).toUpperCase() : "?";
                  const authorName = comment.author || "Unknown";

                  return (
                    <div
                      key={comment.comment_id}
                      className="bg-gray-50 rounded-lg p-4"
                    >
                      <div className="flex items-start gap-3 mb-3">
                        <div className="bg-purple-100 text-purple-700 rounded-full w-10 h-10 flex items-center justify-center font-bold flex-shrink-0">
                          {authorInitial}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="font-semibold text-gray-800">
                              u/{authorName}
                            </span>
                            <span className="text-gray-400">•</span>
                            <span className="text-sm text-gray-600">
                              on: {post?.title ? post.title.substring(0, 50) : "Unknown post"}...
                            </span>
                          </div>
                          <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                            {comment.body || "No content"}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}