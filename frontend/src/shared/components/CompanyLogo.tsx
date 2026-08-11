/**
 * Marca de la empresa en la barra lateral.
 *
 * El archivo `public/logo-empresa.svg` se agrega más adelante; mientras no
 * exista se muestra la marca por defecto con la inicial de la empresa.
 */

import { School } from '@mui/icons-material';
import { Avatar, Box, Stack, Typography } from '@mui/material';
import { useState } from 'react';

const LOGO_SRC = '/logo-empresa.svg';

export function CompanyLogo({ companyName }: { companyName?: string | null }) {
  const [logoFailed, setLogoFailed] = useState(false);

  return (
    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ minWidth: 0 }}>
      {logoFailed ? (
        <Avatar
          variant="rounded"
          sx={{ width: 36, height: 36, bgcolor: 'primary.main', fontWeight: 700 }}
        >
          {companyName?.trim()?.[0]?.toUpperCase() ?? <School fontSize="small" />}
        </Avatar>
      ) : (
        <Box
          component="img"
          src={LOGO_SRC}
          alt={companyName ?? 'Logo de la empresa'}
          onError={() => setLogoFailed(true)}
          sx={{ width: 36, height: 36, objectFit: 'contain', borderRadius: 1.5 }}
        />
      )}
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h5" noWrap sx={{ lineHeight: 1.2 }}>
          {companyName ?? 'Nexora'}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap display="block">
          Nexora
        </Typography>
      </Box>
    </Stack>
  );
}
