import { Component, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
class Boundary extends Component<{ children: ReactNode; destination: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(previous: { destination: string }) {
    if (this.state.error && previous.destination !== this.props.destination) this.setState({ error: null });
  }
  render() {
    if (this.state.error) return <div role="alert" className="card space-y-3"><h1 className="font-bold">This page could not render.</h1><p>{this.state.error.message}</p><button className="action" onClick={() => this.setState({ error: null })}>Retry</button><button onClick={() => window.location.reload()}>Reload</button></div>;
    return this.props.children;
  }
}
export function RouteBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <Boundary destination={location.pathname + location.search}>{children}</Boundary>;
}
