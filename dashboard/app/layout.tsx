export const metadata = { title: "AInterceptor — Governance" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0d1117", color: "#e6edf3" }}>
        {children}
      </body>
    </html>
  );
}
