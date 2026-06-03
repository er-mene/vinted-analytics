import { useEffect, useState, useRef } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): { data: T | null; error: string | null; isLoading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const mounted = useRef(true);

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
  }, [fetcher, intervalMs]);

  return { data, error, isLoading };
}
