const OWNER = process.env.GITHUB_OWNER || "arunramakantsingh-coder";
const REPO  = process.env.GITHUB_REPO  || "AInterceptor";
const TOKEN = process.env.GITHUB_TOKEN;

export type Commit = {
  sha: string;
  short: string;
  message: string;
  author: string;
  date: string;
  url: string;
};

export async function listCommits(limit = 30): Promise<Commit[]> {
  const headers: Record<string,string> = { "Accept": "application/vnd.github+json" };
  if (TOKEN) headers["Authorization"] = `Bearer ${TOKEN}`;

  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/commits?per_page=${limit}`,
    { headers, next: { revalidate: 60 } }
  );
  if (!res.ok) throw new Error(`GitHub API ${res.status}`);
  const data = await res.json();
  return data.map((c: any) => ({
    sha: c.sha,
    short: c.sha.slice(0,7),
    message: (c.commit.message || "").split("\n")[0],
    author: c.commit.author?.name || "unknown",
    date: c.commit.author?.date || "",
    url: c.html_url,
  }));
}
