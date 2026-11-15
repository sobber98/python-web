import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { FullPageLoader } from '@/components/ui/Feedback'
import { useSession } from '@/lib/queries'

export function ProtectedRoute() {
  const { data, isLoading, isError } = useSession()
  const location = useLocation()

  if (isLoading) return <FullPageLoader />
  if (isError || !data?.authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return <Outlet />
}
