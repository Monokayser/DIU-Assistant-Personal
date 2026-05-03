import { Sparkles, GraduationCap, BookOpen, Award } from "lucide-react";

export const MODE_ICONS = {
  assistant: Sparkles,
  admission: GraduationCap,
  course: BookOpen,
  scholarship: Award,
};

const SUGGESTION_COUNT = 4;

export const WELCOME_SUGGESTION_POOLS = {
  assistant: {
    suggestions: [
      { label: "Explore Programs", prompt: "What undergraduate and postgraduate programs are offered at DIU?" },
      { label: "Campus Facilities", prompt: "Tell me about DIU campus facilities, libraries, labs, and student resources." },
      { label: "DIU Overview", prompt: "Give me a clear overview of Daffodil International University." },
      { label: "Faculties at DIU", prompt: "Which faculties and departments are available at DIU?" },
      { label: "Student Life", prompt: "What is student life like at DIU?" },
      { label: "Permanent Campus", prompt: "Tell me about DIU's permanent campus and Daffodil Smart City." },
      { label: "Contact Info", prompt: "How can I contact DIU admission or student support?" },
      { label: "Academic Calendar", prompt: "What should I know about DIU semesters and academic calendar planning?" },
      { label: "Transport Facilities", prompt: "What transport facilities are available for DIU students?" },
      { label: "Residential Halls", prompt: "What residential or hostel facilities does DIU provide?" },
      { label: "Clubs & Activities", prompt: "What clubs, events, and extracurricular activities are available at DIU?" },
      { label: "Research at DIU", prompt: "Tell me about research, innovation, and lab opportunities at DIU." },
      { label: "Career Support", prompt: "What career support and employability services does DIU offer?" },
      { label: "International Students", prompt: "What support does DIU provide for international students?" },
      { label: "Why DIU?", prompt: "What are the strongest reasons to choose DIU?" },
      { label: "Rankings", prompt: "What are DIU's latest rankings and recognitions?" },
      { label: "Library Services", prompt: "What library and digital learning resources are available at DIU?" },
      { label: "IT Support", prompt: "What IT, portal, and online learning systems do DIU students use?" },
      { label: "Campus Safety", prompt: "What safety, health, and student welfare services are available at DIU?" },
      { label: "Quick Guide", prompt: "Give me a quick beginner's guide for a new DIU student." },
    ],
  },
  admission: {
    suggestions: [
      { label: "Undergraduate Requirements", prompt: "What are the minimum GPA requirements for applying to undergraduate programs at DIU?" },
      { label: "Application Process", prompt: "Can you guide me through the DIU admission process step by step?" },
      { label: "Required Documents", prompt: "What documents do I need to prepare for my DIU admission application?" },
      { label: "Admission Deadlines", prompt: "When are DIU admission deadlines for the upcoming semester?" },
      { label: "CSE Eligibility", prompt: "What are the admission requirements for CSE at DIU?" },
      { label: "SWE Eligibility", prompt: "What are the admission requirements for Software Engineering at DIU?" },
      { label: "BBA Admission", prompt: "What are the admission requirements for BBA at DIU?" },
      { label: "Diploma Students", prompt: "Can diploma students apply to DIU, and what is the process?" },
      { label: "Credit Transfer", prompt: "How does admission with credit transfer work at DIU?" },
      { label: "International Students", prompt: "What is the admission procedure for international applicants at DIU?" },
      { label: "Admission Fees", prompt: "What fees should a new applicant expect during DIU admission?" },
      { label: "Online Application", prompt: "How do I apply online for admission at DIU?" },
      { label: "Admission Test", prompt: "Does DIU require an admission test or interview?" },
      { label: "Low GPA Options", prompt: "Can I apply to DIU if my SSC or HSC GPA is low?" },
      { label: "Science Background", prompt: "Which DIU programs require a science background?" },
      { label: "English Requirement", prompt: "Are there English requirements or remedial courses for new DIU students?" },
      { label: "Admission Contact", prompt: "Who should I contact for DIU admission help?" },
      { label: "Semester Intake", prompt: "Which semester intake should I apply for at DIU?" },
      { label: "Program Choice", prompt: "How should I choose the right DIU program before applying?" },
      { label: "Final Checklist", prompt: "Give me a final admission checklist before submitting my DIU application." },
    ],
  },
  course: {
    suggestions: [
      { label: "CSE Curriculum", prompt: "Can you provide an overview of the Computer Science and Engineering (CSE) curriculum?" },
      { label: "SWE Curriculum", prompt: "Can you explain the Software Engineering curriculum at DIU?" },
      { label: "CSE vs SWE", prompt: "Compare CSE and Software Engineering at DIU for career planning." },
      { label: "Credit Transfers", prompt: "What is the policy and process for transferring credits to DIU?" },
      { label: "Postgraduate Options", prompt: "What master's degree programs are currently available at DIU?" },
      { label: "Major & Minor Selection", prompt: "How does major and minor selection work at DIU?" },
      { label: "FSIT Departments", prompt: "Which departments are under the Faculty of Science and Information Technology?" },
      { label: "Engineering Programs", prompt: "What engineering-related programs are available at DIU?" },
      { label: "Course Credits", prompt: "How are course credits structured in DIU undergraduate programs?" },
      { label: "Semester Plan", prompt: "What does a typical semester plan look like for a DIU student?" },
      { label: "Lab Courses", prompt: "Which DIU programs have strong lab and practical course components?" },
      { label: "Cyber Security", prompt: "What cybersecurity-related study options are available at DIU?" },
      { label: "Data Science Path", prompt: "How can a DIU student prepare for data science or AI careers?" },
      { label: "BBA Courses", prompt: "Give me an overview of the BBA program structure at DIU." },
      { label: "English Courses", prompt: "What English or communication courses do DIU students take?" },
      { label: "Internship Rules", prompt: "How do internships or project courses usually work at DIU?" },
      { label: "Thesis vs Project", prompt: "What is the difference between thesis, project, and internship options?" },
      { label: "Program Demand", prompt: "Which DIU departments are most demandable for tech careers?" },
      { label: "Curriculum Details", prompt: "How can I find detailed curriculum and course outline information for a DIU department?" },
      { label: "Career Roadmap", prompt: "Build me a course and skill roadmap for a DIU CSE student." },
    ],
  },
  scholarship: {
    suggestions: [
      { label: "Merit-Based Waivers", prompt: "How much waiver can I get based on my SSC and HSC GPA results?" },
      { label: "CSE Waiver Rules", prompt: "What are the specific waiver rules for CSE students at DIU?" },
      { label: "Need-Based Aid", prompt: "What financial aid options are available for students requiring financial assistance?" },
      { label: "Maintain Scholarship", prompt: "What CGPA or SGPA must I maintain to keep my DIU scholarship active?" },
      { label: "Sibling Waiver", prompt: "Can you explain the criteria for sibling waivers at DIU?" },
      { label: "Corporate Waiver", prompt: "What is the corporate waiver policy at DIU?" },
      { label: "Golden GPA-5", prompt: "What waiver can I get for Golden GPA-5 in SSC and HSC?" },
      { label: "GPA-5 Waiver", prompt: "What waiver can I get if I have GPA-5 in HSC or both SSC and HSC?" },
      { label: "Quota Waiver", prompt: "What quota-based scholarship or waiver options are available at DIU?" },
      { label: "Freedom Fighter Quota", prompt: "How does the freedom fighter quota scholarship work at DIU?" },
      { label: "Sports & Talent", prompt: "Are there sports, talent, or extracurricular scholarships at DIU?" },
      { label: "Female Students", prompt: "Are there any special scholarship options for female students at DIU?" },
      { label: "Waiver Calculator", prompt: "Help me estimate my DIU tuition waiver from my SSC and HSC results." },
      { label: "Scholarship Documents", prompt: "What documents are needed to apply for DIU scholarship or financial aid?" },
      { label: "Renewal Rules", prompt: "How do scholarship renewal and cancellation rules work at DIU?" },
      { label: "Tuition Fees", prompt: "How do tuition fees and waivers combine for a DIU program?" },
      { label: "Poor Fund", prompt: "Does DIU offer poor fund or need-based financial support?" },
      { label: "Waiver Exceptions", prompt: "What exceptions or special cases exist in DIU waiver policies?" },
      { label: "Program Differences", prompt: "Do waiver rules differ between CSE, SWE, Pharmacy, and other programs?" },
      { label: "Best Aid Option", prompt: "Which scholarship or waiver option should I apply for at DIU?" },
    ],
  },
};

export const WELCOME_CONTENT_BASE = {
  assistant: {
    title: "DIU Assistant",
    subtitle: "Your intelligent guide to Daffodil International University.",
  },
  admission: {
    title: "DIU Admission",
    subtitle: "Guidance on requirements, deadlines, and application procedures.",
  },
  course: {
    title: "DIU Courses",
    subtitle: "Explore academic programs, curriculum details, and credit requirements.",
  },
  scholarship: {
    title: "DIU Scholarship",
    subtitle: "Information on tuition waivers, financial aid, and eligibility criteria.",
  },
};

function sampleSuggestions(pool, count = SUGGESTION_COUNT) {
  const available = Array.isArray(pool) ? [...pool] : [];
  for (let index = available.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [available[index], available[swapIndex]] = [available[swapIndex], available[index]];
  }
  return available.slice(0, count);
}

export function buildWelcomeContent(modeKey) {
  const key = WELCOME_CONTENT_BASE[modeKey] ? modeKey : "assistant";
  return {
    ...WELCOME_CONTENT_BASE[key],
    suggestions: sampleSuggestions(WELCOME_SUGGESTION_POOLS[key]?.suggestions),
  };
}

export const WELCOME_CONTENT = Object.fromEntries(
  Object.keys(WELCOME_CONTENT_BASE).map((key) => [key, buildWelcomeContent(key)])
);
