import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import type { Category, CategoryCreate } from '../../api/types';
import { useAuthState } from '../../app/useAuthState';

export const CATEGORIES_KEY = ['categories'] as const;

const bySortOrder = (a: Category, b: Category) => a.sort_order - b.sort_order;

/** All categories (including hidden ones), ordered by `sort_order`. */
export function useCategories() {
  return useQuery({
    queryKey: CATEGORIES_KEY,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/categories'))
        .slice()
        .sort(bySortOrder),
  });
}

/** Lookup by id; stable while the category list is unchanged. */
export function categoryMap(categories: readonly Category[] | undefined): Map<string, Category> {
  return new Map((categories ?? []).map((c) => [c.id, c]));
}

/**
 * The category to preselect for a new event: the user's last used one (`me.last_category_id`)
 * when it still exists, otherwise the first category. `undefined` while nothing is loaded.
 */
export function useDefaultCategoryId(): string | undefined {
  const { data: categories } = useCategories();
  const { data: auth } = useAuthState();
  const last = auth?.user?.last_category_id;
  if (last && categories?.some((c) => c.id === last)) return last;
  return categories?.[0]?.id;
}

/** Body of a new category; `hidden` and `is_leave` default to false on the server. */
export type NewCategory = Pick<CategoryCreate, 'name' | 'colour'> & Partial<CategoryCreate>;

/** `POST /categories`. */
export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: NewCategory) =>
      unwrap(await api.POST('/api/v1/categories', { body: body as CategoryCreate })),
    onSuccess: () => qc.invalidateQueries({ queryKey: CATEGORIES_KEY }),
  });
}

export interface CategoryPatch {
  name?: string;
  colour?: Category['colour'];
  is_leave?: boolean;
  hidden?: boolean;
}

/**
 * `PATCH /categories/{id}` with the optimistic-concurrency `version`. The cache is updated
 * immediately and rolled back on failure.
 */
export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({ category, patch }: { category: Category; patch: CategoryPatch }) =>
      unwrap(
        await api.PATCH('/api/v1/categories/{category_id}', {
          params: { path: { category_id: category.id } },
          body: { ...patch, version: category.version },
        }),
      ),
    onMutate: async ({ category, patch }) => {
      await qc.cancelQueries({ queryKey: CATEGORIES_KEY });
      const previous = qc.getQueryData<Category[]>(CATEGORIES_KEY);
      qc.setQueryData<Category[]>(CATEGORIES_KEY, (list) =>
        list?.map((c) => (c.id === category.id ? { ...c, ...patch } : c)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) qc.setQueryData(CATEGORIES_KEY, context.previous);
    },
    onSuccess: (updated) => {
      qc.setQueryData<Category[]>(CATEGORIES_KEY, (list) =>
        list?.map((c) => (c.id === updated.id ? updated : c)),
      );
    },
    onSettled: (_data, _error, { patch }) => {
      // Vacation flags are recomputed on the server without bumping event versions.
      if (patch.is_leave !== undefined) {
        void qc.invalidateQueries({ queryKey: ['occurrences'] });
        void qc.invalidateQueries({ queryKey: ['leave'] });
      }
      return qc.invalidateQueries({ queryKey: CATEGORIES_KEY });
    },
  });
}

/** `DELETE /categories/{id}?reassign_to=`; events are moved to `reassignTo` first. */
export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({ id, reassignTo }: { id: string; reassignTo?: string }) => {
      unwrap(
        await api.DELETE('/api/v1/categories/{category_id}', {
          params: { path: { category_id: id }, query: { reassign_to: reassignTo } },
        }),
      );
    },
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: CATEGORIES_KEY }),
        qc.invalidateQueries({ queryKey: ['occurrences'] }),
      ]),
  });
}

/** `PUT /categories/order` with the full id list in the new order. */
export function useReorderCategories() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (ids: string[]) =>
      unwrap(await api.PUT('/api/v1/categories/order', { body: { ids } })),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: CATEGORIES_KEY });
      const previous = qc.getQueryData<Category[]>(CATEGORIES_KEY);
      qc.setQueryData<Category[]>(CATEGORIES_KEY, (list) =>
        list
          ? ids
              .map((id, index) => {
                const c = list.find((x) => x.id === id);
                return c ? { ...c, sort_order: index } : undefined;
              })
              .filter((c): c is Category => c !== undefined)
          : list,
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) qc.setQueryData(CATEGORIES_KEY, context.previous);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: CATEGORIES_KEY }),
  });
}
