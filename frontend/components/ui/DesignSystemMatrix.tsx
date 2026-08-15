"use client";

import { useState } from "react";
import { AlertTriangle, Check, LoaderCircle, Save, Search } from "lucide-react";
import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Flash,
  Group,
  Heading,
  IconButton,
  Label,
  Modal,
  PasswordInput,
  Select,
  Spinner,
  Stack,
  Surface,
  Text,
  TextInput,
  Textarea,
  ToggleSwitch,
  Tooltip,
} from "@/components/ui/primitives";
import { notify } from "@/lib/notify";
import styles from "./DesignSystemMatrix.module.css";

export function DesignSystemMatrix() {
  const [value, setValue] = useState("");
  const [choice, setChoice] = useState("graphite");
  const [checked, setChecked] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <section data-testid="design-system-matrix" className={styles.matrix}>
      <Stack gap="xl">
        <header>
          <Heading order={1}>Graphite Workbench UI Matrix</Heading>
          <Text>Component contract, states, long labels, and persistent errors.</Text>
        </header>
        <Surface className={styles.surface}>
          <Stack gap="md">
            <Heading order={2}>Controls</Heading>
            <Group className={styles.controls} align="end" wrap>
              <TextInput label="Search model" placeholder="Long label with English and Chinese" value={value} onChange={(event) => setValue(event.currentTarget.value)} leadingVisual={Search} />
              <PasswordInput label="Credential" placeholder="Persistent secret field" />
              <Select label="Theme" value={choice} onValueChange={setChoice}>
                <Select.Option value="graphite">Graphite</Select.Option>
                <Select.Option value="graphite-long">Graphite with a deliberately long option label</Select.Option>
              </Select>
            </Group>
            <Group align="center" wrap>
              <Checkbox label="Keep local draft" checked={checked} onChange={(event) => setChecked(event.currentTarget.checked)} />
              <ToggleSwitch aria-label="Enable auto sync" checked={enabled} onChange={(event) => setEnabled(event.currentTarget.checked)} />
              <IconButton icon={Save} aria-label="Save current settings" />
              <Tooltip text="Search current workspace"><IconButton icon={Search} aria-label="Search current workspace" /></Tooltip>
              <Button variant="primary" leadingVisual={Save}>Save settings</Button>
              <Button variant="secondary" leadingVisual={Check}>Secondary action</Button>
              <Button variant="danger" leadingVisual={AlertTriangle}>Destructive action</Button>
              <Button variant="primary" leadingVisual={LoaderCircle} disabled>Loading</Button>
            </Group>
            <Textarea label="Notes" rows={3} value={value} onChange={(event) => setValue(event.target.value)} />
          </Stack>
        </Surface>
        <Surface className={styles.surface}>
          <Stack gap="md">
            <Heading order={2}>States</Heading>
            <Group wrap>
              <Label variant="success">Saved</Label>
              <Label variant="warning">Needs review</Label>
              <Label variant="danger">Failed</Label>
              <Flash variant="success" title="Success">Operation completed.</Flash>
              <Alert color="red" title="Field error">Error notifications remain until explicitly dismissed.</Alert>
              <Spinner size="medium" aria-label="Loading" />
            </Group>
            <Group>
              <Button onClick={() => notify.error({ title: "Matrix error", description: "This notification will not auto-close." })}>Trigger persistent error</Button>
              <Button variant="secondary" onClick={() => setDialogOpen(true)}>Open Dialog</Button>
              <Button variant="secondary" onClick={() => setDrawerOpen(true)}>Open Drawer</Button>
            </Group>
          </Stack>
        </Surface>
      </Stack>
      <Modal opened={dialogOpen} onClose={() => setDialogOpen(false)} title="Dialog state matrix">
        <Text>Dialog content must preserve focus and close behavior.</Text>
      </Modal>
      <Drawer opened={drawerOpen} onClose={() => setDrawerOpen(false)} title="Drawer state matrix" position="right">
        <Text>Drawer content must not create horizontal overflow on narrow screens.</Text>
      </Drawer>
    </section>
  );
}
