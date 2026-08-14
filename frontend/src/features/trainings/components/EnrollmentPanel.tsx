/** Asignación de la capacitación a usuarios y seguimiento de su avance. */

import { Delete, PersonAdd } from '@mui/icons-material';
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Enrollment, Paginated, User } from '@/shared/api/types';
import { ConfirmDialog, Loading, ProgressBar, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { formatDate, progressValue } from '@/shared/utils/format';

export function EnrollmentPanel({ trainingId }: { trainingId: string }) {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [selected, setSelected] = useState<User[]>([]);
  const [toRemove, setToRemove] = useState<Enrollment | null>(null);

  const enrollments = useQuery({
    queryKey: ['training', trainingId, 'enrollments'],
    queryFn: async () =>
      (await api.get<Enrollment[]>(endpoints.trainings.enrollments(trainingId))).data,
  });

  const users = useQuery({
    queryKey: ['users', { active: true }],
    queryFn: async () =>
      (await api.get<Paginated<User>>(endpoints.users.list, { params: { is_active: true, page_size: 100 } }))
        .data,
  });

  const assign = useMutation({
    mutationFn: (userIds: string[]) =>
      api.post(endpoints.trainings.enrollments(trainingId), { user_ids: userIds }),
    onSuccess: async ({ data }) => {
      await queryClient.invalidateQueries({ queryKey: ['training', trainingId, 'enrollments'] });
      setSelected([]);
      snackbar.success(`${data.assigned_count} usuario(s) asignado(s).`);
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: (enrollmentId: string) => api.delete(endpoints.enrollments.detail(enrollmentId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['training', trainingId, 'enrollments'] });
      setToRemove(null);
      snackbar.success('Participante quitado de la capacitación.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (enrollments.isLoading) return <Loading />;

  const assignedIds = new Set(enrollments.data?.map((item) => item.user.id) ?? []);
  const candidates = (users.data?.results ?? []).filter((user) => !assignedIds.has(user.id));

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="h4" gutterBottom>
            Asignar participantes
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mt: 2 }}>
            <Autocomplete
              multiple
              sx={{ flex: 1 }}
              options={candidates}
              value={selected}
              onChange={(_, value) => setSelected(value)}
              getOptionLabel={(option) => `${option.full_name} (${option.email})`}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              renderInput={(inputParams) => (
                <TextField {...inputParams} label="Usuarios" placeholder="Buscar por nombre o correo" />
              )}
            />
            <Button
              variant="contained"
              startIcon={<PersonAdd />}
              disabled={selected.length === 0 || assign.isPending}
              onClick={() => assign.mutate(selected.map((user) => user.id))}
              sx={{ alignSelf: { sm: 'flex-start' }, height: 40, flexShrink: 0 }}
            >
              Asignar
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent sx={{ p: 0 }}>
          <Box sx={{ p: { xs: 2, sm: 3 }, pb: 1 }}>
            <Typography variant="h4">
              Participantes ({enrollments.data?.length ?? 0})
            </Typography>
          </Box>

          {(enrollments.data?.length ?? 0) === 0 ? (
            <Box sx={{ p: { xs: 2, sm: 3 }, pt: 0 }}>
              <Typography variant="body2" color="text.secondary">
                Aún no hay usuarios asignados a esta capacitación.
              </Typography>
            </Box>
          ) : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 700 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Usuario</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell sx={{ minWidth: 180 }}>Avance</TableCell>
                    <TableCell>Asignado</TableCell>
                    <TableCell>Completado</TableCell>
                    <TableCell align="right">Acciones</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {enrollments.data!.map((enrollment) => (
                    <TableRow key={enrollment.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={600}>
                          {enrollment.user.full_name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {enrollment.user.email}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <StatusChip status={enrollment.status} />
                      </TableCell>
                      <TableCell>
                        <ProgressBar
                          value={progressValue(enrollment.progress)}
                          label=""
                          color={enrollment.status === 'COMPLETED' ? 'success' : 'primary'}
                        />
                      </TableCell>
                      <TableCell>{formatDate(enrollment.assigned_at)}</TableCell>
                      <TableCell>{formatDate(enrollment.completed_at)}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          color="error"
                          aria-label={`Quitar a ${enrollment.user.full_name}`}
                          onClick={() => setToRemove(enrollment)}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={toRemove !== null}
        title="Quitar participante"
        message={`Se quitará a ${toRemove?.user.full_name ?? ''} de esta capacitación junto con su avance registrado. Esta acción no se puede deshacer.`}
        confirmLabel="Quitar"
        destructive
        loading={remove.isPending}
        onConfirm={() => toRemove && remove.mutate(toRemove.id)}
        onCancel={() => setToRemove(null)}
      />
    </Stack>
  );
}
