export interface Author {
  name: string;
  initials: string;
  photo: string;
  title: string;
  company: string;
  linkedin: string;
  twitter: string;
  github: string;
}

export const AUTHORS: Author[] = [
  {
    name: "Giannis Kotsakiachidis",
    initials: "GK",
    photo: "/images/giannis.jpg",
    title: "Solution Engineer",
    company: "Palm",
    linkedin: "https://www.linkedin.com/in/gianniskotsas/",
    twitter: "https://x.com/gianniskotsas",
    github: "https://github.com/gianniskotsas",
  },
  {
    name: "Kostas Krachtopoulos",
    initials: "KK",
    photo: "/images/kostas.jpg",
    title: "Data Science",
    company: "Booking.com",
    linkedin: "https://www.linkedin.com/in/konstantinoskrachtopoulos/",
    twitter: "https://x.com/thisiskostas",
    github: "https://github.com/kostaskracht",
  },
];
