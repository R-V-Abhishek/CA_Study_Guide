import { accountKey, apiRequest } from '@caf/api-client';
export async function exportProfile() {
  const data = await apiRequest<unknown>('/api/v1/me/export');
  const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{ type:'application/json' }));
  const link = document.createElement('a'); link.href=url; link.download=`study-profile-${accountKey()}.json`; link.click(); URL.revokeObjectURL(url);
}
