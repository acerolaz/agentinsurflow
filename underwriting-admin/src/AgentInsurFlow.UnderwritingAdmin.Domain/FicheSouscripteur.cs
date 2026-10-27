namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Fiche du lead dans le détail du dossier (exception à la minimisation, 27/10) : jamais vers le cluster ni un LLM.</summary>
public sealed record FicheSouscripteur(string Civilite, string Nom, string Prenom, string Adresse, string CodePostal,
    string Mobile, string Email, VehiculeContrat? Vehicule);
