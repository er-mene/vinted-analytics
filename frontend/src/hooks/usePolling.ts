import { useEffect, useState, useRef, useCallback } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  refetch: () => void;
  mutate: React.Dispatch<React.SetStateAction<T | null>>;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pollIndex, setPollIndex] = useState(0);
  const mounted = useRef(true);

  const refetch = useCallback(() => {
    setPollIndex((i) => i + 1);
  }, []);

  useEffect(() => {
    mounted.current = true;

    const poll = async () => {
      try {
        const result = await fetcher();
        if (mounted.current) {
          setData(result);
          setError(null);
        }
      } catch (e: unknown) {
        if (mounted.current) {
          setError(e instanceof Error ? e.message : "Unknown error");
        }
      } finally {
        if (mounted.current) setIsLoading(false);
      }
    };

    poll();
    const id = setInterval(poll, intervalMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [fetcher, intervalMs, pollIndex]);

  return { data, error, isLoading, refetch, mutate: setData };
}
