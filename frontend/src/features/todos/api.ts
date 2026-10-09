import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import type { Todo, TodoCreate, TodoUpdate } from '../../api/types';

/** Root of every to-do query: `['todos', 'range', from, to]` and `['todos', 'due']`. */
export const TODOS_KEY = ['todos'] as const;

/** To-dos listed on the days `[from, to]` (open ones carry over to today, done ones stay). */
export function useTodos(from: string, to: string) {
  return useQuery({
    queryKey: [...TODOS_KEY, 'range', from, to] as const,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/todos', { params: { query: { from, to } } })).todos,
  });
}

/** Open to-dos due today or overdue (the pop-up). */
export function useDueTodos() {
  return useQuery({
    queryKey: [...TODOS_KEY, 'due'] as const,
    queryFn: async () => unwrap(await api.GET('/api/v1/todos/due')).todos,
  });
}

const refresh = (qc: QueryClient) => qc.invalidateQueries({ queryKey: TODOS_KEY });

export function useCreateTodo() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: TodoCreate) => unwrap(await api.POST('/api/v1/todos', { body })),
    onSettled: () => refresh(qc),
  });
}

export interface UpdateTodoVariables {
  id: string;
  patch: TodoUpdate;
}

/** `PATCH /todos/{id}`. Checking a box is applied to every cached list at once. */
export function useUpdateTodo() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({ id, patch }: UpdateTodoVariables) =>
      unwrap(
        await api.PATCH('/api/v1/todos/{todo_id}', {
          params: { path: { todo_id: id } },
          body: patch,
        }),
      ),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: TODOS_KEY });
      const snapshot = qc.getQueriesData<Todo[]>({ queryKey: TODOS_KEY });
      const done = patch.done;
      if (done !== undefined && done !== null) {
        for (const [key, data] of snapshot) {
          qc.setQueryData<Todo[] | undefined>(
            key,
            data?.map((t) => (t.id === id ? { ...t, done } : t)),
          );
        }
      }
      return { snapshot };
    },
    onError: (_error, _vars, context) => {
      for (const [key, data] of context?.snapshot ?? []) qc.setQueryData(key, data);
    },
    onSettled: () => refresh(qc),
  });
}

export function useDeleteTodo() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (id: string) => {
      unwrap(await api.DELETE('/api/v1/todos/{todo_id}', { params: { path: { todo_id: id } } }));
    },
    onSettled: () => refresh(qc),
  });
}
