import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError, registerTokenGetter, registerUnauthorizedHandler } from './api/client';
import { getStoredToken, useAuthStore } from './stores/authStore';
import { AppRouter } from './router';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 인증·권한 오류는 재시도하지 않는다. 그 외 일시 오류만 1회 재시도.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && failureCount < 1,
      refetchOnWindowFocus: false,
    },
  },
});

// API 요청에 JWT를 싣고(docs/10-implementation-guide.md §9.3), 세션 만료(401) 시 로그아웃한다.
registerTokenGetter(getStoredToken);
registerUnauthorizedHandler(() => {
  useAuthStore.getState().logout();
  queryClient.clear();
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppRouter />
    </QueryClientProvider>
  );
}

export default App;
