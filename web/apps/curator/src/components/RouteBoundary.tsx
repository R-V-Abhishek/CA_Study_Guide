import { Component, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="p-6 rounded-xl border border-rose-800 space-y-3">
      <h1 className="font-bold">This page could not be displayed.</h1>
      <p className="text-sm">Use the navigation to open another page, or retry.</p>
      <button onClick={() => this.setState({ failed: false })} className="underline mr-4">Retry page</button>
      <button onClick={() => window.location.reload()} className="underline">Reload</button>
    </div>;
    return this.props.children;
  }
}
export function RouteBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <Boundary key={location.pathname}>{children}</Boundary>;
}
