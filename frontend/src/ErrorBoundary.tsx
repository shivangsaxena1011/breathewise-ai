import { Component, type ReactNode } from "react";

/** Keeps one broken page (or a stale code chunk after a redeploy) from blanking the whole app. */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: false });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="card empty" role="alert" style={{ marginTop: 18 }}>
        <div className="leaf" aria-hidden="true">🍂</div>
        <p>Something went wrong on this page. / इस पेज में कुछ गड़बड़ हुई।</p>
        <button className="btn" onClick={() => window.location.reload()}>Reload / फिर से लोड करें</button>
      </div>
    );
  }
}
