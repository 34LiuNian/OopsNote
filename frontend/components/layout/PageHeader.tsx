import { Box, Heading, Text } from "@/components/ui/primitives";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Box className="page-header" sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 3, flexWrap: "wrap" }}>
      <Box>
        <Heading as="h1" sx={{ fontSize: 4, m: 0 }}>{title}</Heading>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>{description}</Text>
      </Box>
      {action}
    </Box>
  );
}
