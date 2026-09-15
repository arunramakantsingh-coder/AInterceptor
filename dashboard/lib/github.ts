const OWNER = process.env.GITHUB_OWNER || "arunramakantsingh-coder";
const REPO  = process.env.GITHUB_REPO  || "AInterceptor";
const TOKEN = process.env.GITHUB_TOKEN;

const H: Record<string,string> = { "Accept": "application/vnd.github+json" };
if (TOKEN) H["Authorization"] = `Bearer ${TOKEN}`;

export type Commit = {
  sha: string; short: string; message: string;
  author: string; date: string; url: string;
};

export type CommitDetail = Commit & {
  body: string;
  files: { filename: string; status: string; additions: number; deletions: number; patch?: string }[];
};

export type Tag = { name: string; sha: string; url: string };

export type CompareCommit = {
  sha: string; short: string; message: string; author: string; date: string;
};

export type CompareFile = {
  filename: string; status: string; additions: number; deletions: number;
};

export type CompareResult = {
  status: string;
  ahead_by: number;
  behind_by: number;
  total_commits: number;
  commits: CompareCommit[];
  files: CompareFile[];
};

async function gh(path: string) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: H, cache: "no-store"
  });
  if (!res.ok) throw new Error(`GitHub ${res.status} ${path}`);
  return res.json();
}

export async function listCommits(limit = 30): Promise<Commit[]> {
  const data: any[] = await gh(`/repos/${OWNER}/${REPO}/commits?per_page=${limit}`);
  return data.map((c: any) => ({
    sha: c.sha, short: c.sha.slice(0,7),
    message: (c.commit.message||"").split("\n")[0],
    author: c.commit.author?.name||"unknown",
    date: c.commit.author?.date||"", url: c.html_url,
  }));
}

export async function getCommit(sha: string): Promise<CommitDetail> {
  const c: any = await gh(`/repos/${OWNER}/${REPO}/commits/${sha}`);
  return {
    sha: c.sha, short: c.sha.slice(0,7),
    message: (c.commit.message||"").split("\n")[0],
    body: c.commit.message||"",
    author: c.commit.author?.name||"unknown",
    date: c.commit.author?.date||"", url: c.html_url,
    files: (c.files||[]).map((f: any) => ({
      filename: f.filename, status: f.status,
      additions: f.additions||0, deletions: f.deletions||0,
      patch: f.patch,
    })),
  };
}

export async function compareCommits(base: string, head: string): Promise<CompareResult> {
  const c: any = await gh(`/repos/${OWNER}/${REPO}/compare/${base}...${head}`);
  const commits: CompareCommit[] = (c.commits||[]).map((x: any) => ({
    sha: x.sha, short: x.sha.slice(0,7),
    message: (x.commit.message||"").split("\n")[0],
    author: x.commit.author?.name||"unknown",
    date: x.commit.author?.date||"",
  }));
  const files: CompareFile[] = (c.files||[]).map((f: any) => ({
    filename: f.filename, status: f.status,
    additions: f.additions||0, deletions: f.deletions||0,
  }));
  return {
    status: c.status,
    ahead_by: c.ahead_by, behind_by: c.behind_by,
    total_commits: c.total_commits,
    commits, files,
  };
}

export async function listTags(): Promise<Tag[]> {
  const t: any[] = await gh(`/repos/${OWNER}/${REPO}/tags?per_page=50`);
  return t.map((x: any) => ({ name: x.name, sha: x.commit.sha, url: x.commit.url }));
}
