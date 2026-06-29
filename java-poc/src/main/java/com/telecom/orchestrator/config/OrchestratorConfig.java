package com.telecom.orchestrator.config;

import com.telecom.orchestrator.pipeline.PipelineEngine;
import com.telecom.orchestrator.store.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import java.nio.file.Path;

@Configuration
public class OrchestratorConfig {

    @Bean
    public KnowledgeBase knowledgeBase() {
        return new KnowledgeBase();
    }

    @Bean
    public PatternStore patternStore(JdbcTemplate jdbcTemplate) {
        return new PatternStore(jdbcTemplate);
    }

    @Bean
    public ServiceModelStore serviceModelStore(JdbcTemplate jdbcTemplate) {
        return new ServiceModelStore(jdbcTemplate);
    }

    @Bean
    public SubscriberLock subscriberLock(JdbcTemplate jdbcTemplate) {
        return new SubscriberLock(jdbcTemplate);
    }

    @Bean
    public DSLStore dslStore() {
        return new DSLStore(Path.of("knowledge-base", "dsl-definitions"));
    }

    @Bean
    public PipelineEngine pipelineEngine(PatternStore patterns, DSLStore dslStore,
                                         ServiceModelStore serviceModels, SubscriberLock subscriberLock) {
        return new PipelineEngine(patterns, dslStore, serviceModels, subscriberLock);
    }
}
