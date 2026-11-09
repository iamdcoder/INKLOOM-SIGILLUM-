"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, FilePlus2, Files, PencilLine } from "lucide-react";
import { api } from "@/lib/api";

type Item = {
  id: string;
  title: string;
  status: string;
  channel: string;
  publication_at: string;
  created_at: string;
  filename: string | null;
  version: number | null;
};

export default function SubmissionsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Item[]>("/submissions").then(setItems).catch((loadError) => setError(loadError.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="hero-row">
        <div>
          <div className="eyebrow">CONTENT LIFECYCLE</div>
          <h1>Submissions</h1>
          <p className="subhead">Drafts can be resumed; every accepted upload is preserved as an immutable, hash-verified version.</p>
        </div>
        <Link href="/submissions/new" className="button primary"><FilePlus2 size={16} /> New submission</Link>
      </section>
      {error && <div className="alert error">{error}</div>}
      <div className="panel submissions-panel">
        <div className="panel-heading">
          <div><div className="eyebrow">ALL CONTENT</div><h2>{items.length} submissions</h2></div>
          <span className="channel-tag">ACTIVE WORKSPACE</span>
        </div>
        {items.length === 0 ? (
          <div className="empty-state"><Files size={28} /><h3>Your submission queue is clear</h3><p>Save a draft or upload a PDF, DOCX, TXT, PNG or JPG to begin.</p></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>SUBMISSION</th><th>CHANNEL</th><th>PUBLICATION</th><th>VERSION</th><th>STATUS</th><th></th></tr></thead>
              <tbody>
                {items.map((item) => {
                  const isDraft = item.status === "DRAFT";
                  const destination = isDraft ? `/submissions/new?draft=${item.id}` : `/reviews/${item.id}`;
                  return (
                    <tr key={item.id}>
                      <td>
                        <Link className="submission-name" href={destination}>
                          <span className="file-icon">{isDraft ? <PencilLine size={16} /> : <Files size={16} />}</span>
                          <span><b>{item.title}</b><small>{item.filename || (isDraft ? "Draft · no file uploaded" : "Original unavailable")}</small></span>
                        </Link>
                      </td>
                      <td>{item.channel.replaceAll("_", " ")}</td>
                      <td>{new Date(item.publication_at).toLocaleString()}</td>
                      <td>{item.version ? `v${item.version}` : "—"}</td>
                      <td><span className={`status-pill ${item.status === "APPROVED" ? "success" : isDraft ? "neutral" : "warning"}`}><i />{item.status.replaceAll("_", " ")}</span></td>
                      <td><Link href={destination} className="arrow-link" aria-label={isDraft ? "Resume draft" : "Open review"}><ArrowUpRight size={16} /></Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
