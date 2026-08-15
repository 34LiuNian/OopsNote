import { ReactNode } from "react";
import styles from "./AuthenticationShell.module.css";

export function AuthenticationShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <main className={styles.shell}>
      <section className={styles.formRegion}>
        <div className={styles.formContent}>
          <div className={styles.brand} aria-label="OopsNote"><span aria-hidden="true" />OopsNote</div>
          <header className={styles.heading}><h1>{title}</h1><p>{description}</p></header>
          {children}
        </div>
      </section>
      <aside className={styles.photoRegion} aria-hidden="true">
        <div className={styles.photo} />
      </aside>
    </main>
  );
}
