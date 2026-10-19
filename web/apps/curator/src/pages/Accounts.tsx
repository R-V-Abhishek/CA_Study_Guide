import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest, accountKey, type Account } from '@caf/api-client';
import { WorkspaceSkeleton } from '../components/WorkspaceSkeleton';
import { RequestError } from '../components/RequestError';
import { Dialog } from '../../../../packages/workspace/Dialog';

type Invitation = { id: number; email: string; role: string; expires_at: string; consumed_at: string | null; revoked_at: string | null; target_user_id: number | null; invitation_url?: string };
export function Accounts() {
  const cache = useQueryClient();
  const accounts = useQuery({ queryKey: ['accounts', accountKey()], queryFn: () => apiRequest<Account[]>('/api/v1/admin/accounts') });
  const invitations = useQuery({ queryKey: ['invitations', accountKey()], queryFn: () => apiRequest<Invitation[]>('/api/v1/admin/invitations') });
  const [email, setEmail] = useState('');
  const [link, setLink] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [change, setChange] = useState<{ account: Account; body: { role?: string; status?: string } } | null>(null);
  const perform = async (url: string, method: string, body?: unknown) => {
    if (pending) return;
    setPending(true); setError(null);
    try {
      const response = await apiRequest<Invitation>(url, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      if (response?.invitation_url) setLink(response.invitation_url);
      await cache.invalidateQueries();
      return true;
    } catch (error) { setError(error instanceof Error ? error : new Error('Account action failed.')); return false; }
    finally { setPending(false); }
  };
  return <div className="space-y-6"><h1 className="text-xl font-bold">Accounts</h1><p>Manage invited students, account access and administrator roles.</p>
    <RequestError error={error ?? accounts.error ?? invitations.error} retry={() => { void accounts.refetch(); void invitations.refetch(); }} />
    <button className="primary-action" onClick={() => setInviting(true)}>Invite student</button>
    <Dialog open={inviting} title="Invite student" onClose={() => setInviting(false)}>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void perform('/api/v1/admin/invitations', 'POST', { email }); }}>
      <label>Student email <input className="bg-slate-800 border rounded p-2 ml-3" type="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
      <button className="bg-indigo-600 rounded px-4 py-2 ml-3" disabled={pending}>Create invitation</button>
    </form>
    {link && <label className="block">Copy invitation link <input className="w-full bg-slate-800 border rounded p-2 mt-2" readOnly value={link} onFocus={event => event.target.select()} /></label>}
    {error && <RequestError error={error} />}
    </Dialog>
    <h2 className="font-bold">Accounts</h2>{accounts.isPending && <WorkspaceSkeleton label="Loading accounts…" />}
    {accounts.data?.map(account => <div key={account.id} className="border border-slate-700 rounded p-3 flex flex-wrap gap-4 items-center"><span>{account.name} · {account.email} · {account.status}</span>
      <label>Role <select className="bg-slate-800 p-2" disabled={pending} value={account.role} onChange={event => setChange({ account, body: { role: event.target.value } })}><option value="student">Student</option><option value="administrator">Administrator</option></select></label>
      {account.status !== 'pending_binding' && <button disabled={pending} onClick={() => setChange({ account, body: { status: account.status === 'disabled' ? 'active' : 'disabled' } })}>{account.status === 'disabled' ? 'Restore access' : 'Disable account'}</button>}
    </div>)}
    <h2 className="font-bold">Invitations</h2>{invitations.isPending && <WorkspaceSkeleton label="Loading invitations…" />}{invitations.data?.length === 0 && <p>No invitations have been created.</p>}{invitations.data?.map(invitation => <div key={invitation.id} className="border border-slate-700 rounded p-3 flex gap-4"><span>{invitation.email} · expires {new Date(invitation.expires_at).toLocaleString()} · {invitation.revoked_at ? 'Revoked' : invitation.consumed_at ? 'Used' : 'Pending'}</span>
      {!invitation.revoked_at && !invitation.consumed_at && <button disabled={pending} onClick={() => void perform(`/api/v1/admin/invitations/${invitation.id}/revoke`, 'POST')}>Revoke invitation</button>}
    </div>)}
    <Dialog open={change !== null} title="Confirm account access change" onClose={() => { if (!pending) setChange(null); }}>
      {change && <><p>{change.account.name} · {change.account.email}</p><p>{change.body.role ? `Role: ${change.account.role} → ${change.body.role}` : `Access: ${change.account.status} → ${change.body.status}`}</p><p>This changes the account’s access to the workspace.</p><RequestError error={error} /><div className="controls"><button className="primary-action" disabled={pending} onClick={async () => { if (await perform(`/api/v1/admin/accounts/${change.account.id}`, 'PATCH', change.body)) setChange(null); }}>{pending ? 'Saving…' : 'Confirm change'}</button><button disabled={pending} onClick={() => setChange(null)}>Cancel</button></div></>}
    </Dialog>
  </div>;
}
