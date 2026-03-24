"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

interface Job {
  id: number;
  job_type: string;
  status: "pending" | "running" | "done" | "error";
  params: string | null;
  output_path: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface Avatar {
  id: number;
  customer_name: string;
  prompt: string;
  image_path: string;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  running: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  done: "bg-green-500/20 text-green-300 border-green-500/30",
  error: "bg-red-500/20 text-red-300 border-red-500/30",
};

const JOB_TYPE_LABELS: Record<string, string> = {
  avatar: "🎨 アバター生成",
  voice: "🎤 音声合成",
  talking_head: "🗣️ トーキングヘッド",
  cinematic: "🎬 シネマティック",
  compose: "✂️ 動画合成",
  pipeline: "🚀 フルパイプライン",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[status] || "bg-gray-500/20 text-gray-300"}`}
    >
      {status === "running" && (
        <span className="mr-1.5 h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
      )}
      {status}
    </span>
  );
}

function GenerateAvatarForm({ onSuccess }: { onSuccess: () => void }) {
  const [customerName, setCustomerName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/v1/avatars/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: customerName,
          prompt,
          width: 1024,
          height: 1024,
          num_inference_steps: 30,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage(`✅ ジョブ開始 (ID: ${data.job_id})`);
        setCustomerName("");
        setPrompt("");
        onSuccess();
      } else {
        setMessage(`❌ エラー: ${JSON.stringify(data)}`);
      }
    } catch (err) {
      setMessage(`❌ 接続エラー: APIサーバーに接続できません`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          顧客名 <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={customerName}
          onChange={(e) => setCustomerName(e.target.value)}
          placeholder="例: 株式会社サンプル"
          required
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          プロンプト <span className="text-red-400">*</span>
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="例: ビジネススーツを着た20代の日本人女性、笑顔、プロフェッショナル"
          required
          rows={3}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition resize-none"
        />
      </div>
      {message && (
        <p className="text-sm text-gray-300 bg-gray-800 rounded-lg px-3 py-2">
          {message}
        </p>
      )}
      <button
        type="submit"
        disabled={loading}
        className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold py-2 px-4 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            処理中...
          </>
        ) : (
          "🎨 アバター生成を開始"
        )}
      </button>
    </form>
  );
}

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [activeTab, setActiveTab] = useState<"jobs" | "avatars" | "generate">("jobs");
  const [loading, setLoading] = useState(true);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

  const fetchData = async () => {
    try {
      const [jobsRes, avatarsRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/jobs/`),
        fetch(`${API_BASE}/api/v1/avatars/`),
        fetch(`${API_BASE}/health`),
      ]);
      if (healthRes.ok) setApiStatus("online");
      if (jobsRes.ok) setJobs((await jobsRes.json()).jobs);
      if (avatarsRes.ok) setAvatars((await avatarsRes.json()).avatars);
    } catch {
      setApiStatus("offline");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // 5秒ごとに自動更新 (ジョブステータスのリアルタイム更新)
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const runningJobs = jobs.filter((j) => j.status === "running").length;
  const doneJobs = jobs.filter((j) => j.status === "done").length;

  return (
    <div className="min-h-screen bg-gray-950 text-white font-sans">
      {/* ヘッダー */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-lg">
              🤖
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">cocoro-influencer</h1>
              <p className="text-xs text-gray-400">企業専属AIインフルエンサー生成システム</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                apiStatus === "online"
                  ? "bg-green-500/10 text-green-400 border-green-500/30"
                  : apiStatus === "offline"
                  ? "bg-red-500/10 text-red-400 border-red-500/30"
                  : "bg-gray-500/10 text-gray-400 border-gray-500/30"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  apiStatus === "online" ? "bg-green-400 animate-pulse" : "bg-red-400"
                }`}
              />
              API {apiStatus === "online" ? "オンライン" : apiStatus === "offline" ? "オフライン" : "確認中"}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* サマリーカード */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "総ジョブ数", value: jobs.length, icon: "📋", color: "from-violet-600 to-indigo-600" },
            { label: "実行中", value: runningJobs, icon: "⚡", color: "from-blue-600 to-cyan-600" },
            { label: "完了", value: doneJobs, icon: "✅", color: "from-green-600 to-emerald-600" },
            { label: "アバター数", value: avatars.length, icon: "🎨", color: "from-pink-600 to-rose-600" },
          ].map((card) => (
            <div
              key={card.label}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-2xl">{card.icon}</span>
                <span
                  className={`text-2xl font-bold bg-gradient-to-r ${card.color} bg-clip-text text-transparent`}
                >
                  {card.value}
                </span>
              </div>
              <p className="text-sm text-gray-400">{card.label}</p>
            </div>
          ))}
        </div>

        {/* タブ */}
        <div className="flex gap-1 mb-6 bg-gray-900 p-1 rounded-lg border border-gray-800 w-fit">
          {(["jobs", "avatars", "generate"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
                activeTab === tab
                  ? "bg-violet-600 text-white shadow-lg shadow-violet-500/25"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              {tab === "jobs" ? "📋 ジョブ一覧" : tab === "avatars" ? "🎨 アバター" : "✨ 新規生成"}
            </button>
          ))}
        </div>

        {/* コンテンツ */}
        {activeTab === "jobs" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
              <h2 className="font-semibold">ジョブ履歴</h2>
              <button
                onClick={fetchData}
                className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
              >
                🔄 更新
              </button>
            </div>
            {loading ? (
              <div className="py-12 text-center text-gray-500">読み込み中...</div>
            ) : jobs.length === 0 ? (
              <div className="py-12 text-center text-gray-500">
                <p className="text-4xl mb-3">📭</p>
                <p>ジョブがありません</p>
                <p className="text-sm mt-1">「新規生成」タブからジョブを作成してください</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-800">
                {jobs.map((job) => (
                  <div key={job.id} className="px-6 py-4 hover:bg-gray-800/50 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">
                            {JOB_TYPE_LABELS[job.job_type] || job.job_type}
                          </span>
                          <span className="text-gray-600 text-xs">#{job.id}</span>
                        </div>
                        {job.output_path && (
                          <p className="text-xs text-gray-500 truncate">→ {job.output_path}</p>
                        )}
                        {job.error_message && (
                          <p className="text-xs text-red-400 mt-1 truncate">{job.error_message}</p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <StatusBadge status={job.status} />
                        <span className="text-xs text-gray-600">
                          {new Date(job.created_at).toLocaleString("ja-JP")}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "avatars" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-800">
              <h2 className="font-semibold">生成済みアバター</h2>
            </div>
            {avatars.length === 0 ? (
              <div className="py-12 text-center text-gray-500">
                <p className="text-4xl mb-3">🎨</p>
                <p>アバターがありません</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-6">
                {avatars.map((avatar) => (
                  <div
                    key={avatar.id}
                    className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700 hover:border-violet-500/50 transition-colors group"
                  >
                    <div className="aspect-square bg-gray-700 flex items-center justify-center text-4xl">
                      🤖
                    </div>
                    <div className="p-3">
                      <p className="font-medium text-sm truncate">{avatar.customer_name}</p>
                      <p className="text-xs text-gray-500 truncate mt-0.5">{avatar.prompt}</p>
                      <p className="text-xs text-gray-600 mt-2">
                        {new Date(avatar.created_at).toLocaleDateString("ja-JP")}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "generate" && (
          <div className="max-w-lg">
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-800">
                <h2 className="font-semibold">アバター生成</h2>
                <p className="text-sm text-gray-400 mt-1">
                  FLUX.2 + LoRA でカスタムアバターを生成します
                </p>
              </div>
              <div className="p-6">
                <GenerateAvatarForm
                  onSuccess={() => {
                    setActiveTab("jobs");
                    fetchData();
                  }}
                />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
