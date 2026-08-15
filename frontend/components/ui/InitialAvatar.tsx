import { Avatar } from "@/components/ui/primitives";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
}

export function InitialAvatar({
  name,
  image,
  size = 40,
}: {
  name: string;
  image?: string | null;
  size?: number;
}) {
  const value = initials(name);
  const fontSize = Math.round(size * (value.length > 1 ? 0.43 : 0.53));
  return (
    <Avatar
      src={image || null}
      alt=""
      size={size}
      radius="50%"
      styles={{ root: { background: "var(--bgColor-muted)", color: "var(--fgColor-default)", border: "1px solid var(--borderColor-default)", fontSize, fontWeight: 600 } }}
    >
      {value}
    </Avatar>
  );
}
