import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";

export default function Login() {
  const nav = useNavigate();
  const [username, setU] = useState("admin");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { await login(username, password); nav("/", { replace: true }); }
    catch (ex: any) { setErr(ex.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <form className="login card" onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 18 }}>
          <div className="brand-mark">S</div>
          <div>
            <div className="brand-name">Sentinel</div>
            <div className="brand-sub">Unified CCTV Integration Platform</div>
          </div>
        </div>
        <label>Username<input value={username} onChange={(e) => setU(e.target.value)} autoFocus /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setP(e.target.value)} /></label>
        {err && <div className="error">{err}</div>}
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <div className="muted small" style={{ marginTop: 12 }}>
          Demo roles: admin · supervisor · operator · gsrtc_nodal · auditor
        </div>
      </form>
    </div>
  );
}
