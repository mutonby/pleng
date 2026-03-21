export function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function formatDate(iso: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })
}

export const statusColors: Record<string, string> = {
  staging: 'bg-yellow-600',
  production: 'bg-green-600',
  deploying: 'bg-orange-600',
  generating: 'bg-purple-600',
  stopped: 'bg-gray-600',
  error: 'bg-red-600',
}

export const statusIcons: Record<string, string> = {
  staging: '🟡',
  production: '🟢',
  deploying: '🟠',
  generating: '🟣',
  stopped: '🔴',
  error: '❌',
}
